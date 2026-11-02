"""Gameplay progression, durable sessions and the two-provider trust boundary."""

import json
import os
import tempfile
import time
import unittest
from itertools import cycle
from pathlib import Path
from unittest.mock import AsyncMock, patch

os.environ["GAME_MODE"] = "demo"
os.environ["MASTER_SECRET"] = "ux-test-master-secret-with-at-least-32-characters"

import httpx
from fastapi.testclient import TestClient

import app
from game import Store, progression, secret_for, solve
from provider import OPENCODE_ENDPOINT, GuardReply, completion, live_reply
from security import AbuseLedger
from settings import SESSION_TTL_SECONDS, Settings


class GameplayTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name)
        self.store = Store("ux-test-session-signing-master", self.path / "missions.sqlite3")
        for name, value in (
            ("store", self.store),
            ("ledger", AbuseLedger(self.path / "ledger.sqlite3")),
            ("MODE", "demo"),
            ("ACTION_COOLDOWN_SECONDS", 0),
        ):
            item = patch.object(app, name, value)
            item.start()
            self.addCleanup(item.stop)
        self.client = TestClient(app.app)
        self.addCleanup(self.client.close)
        self.client.post("/api/start", json={"team": "Ada"})
        self.session = next(iter(self.store.sessions.values()))

    def test_first_hint_is_free_and_following_hints_cost_points(self):
        room = self.session.rooms[0]
        state = self.client.post("/api/hint", json={"token": room.hint_token}).json()
        self.assertEqual(len(state["room"]["hints"]), 1)
        solve(self.session)
        self.assertEqual(room.points, 10)
        room.solved = False
        room.hint_ready_at = 0
        self.client.post("/api/hint", json={"token": room.hint_token})
        solve(self.session)
        self.assertEqual(room.points, 9)

    def test_exhaustion_walkthrough_preserves_notes_and_next_station_without_ai(self):
        room = self.session.rooms[0]
        room.round_attempts = 30
        room.note = "Keep my observation"
        with patch.object(app, "live_reply", AsyncMock()) as provider:
            response = self.client.post("/api/assist", json={"station": 0})
        self.assertEqual(response.status_code, 200)
        state = response.json()
        self.assertFalse(state["game_over"])
        self.assertTrue(state["room"]["assisted"])
        self.assertEqual(state["score"], 1)
        self.assertEqual(state["room"]["note"], "Keep my observation")
        self.assertEqual(state["progression"]["xp"], 100)
        self.assertEqual(room.attempts, 0)
        self.assertEqual(room.hints, 0)
        provider.assert_not_called()
        self.assertEqual(self.client.post("/api/assist", json={"station": 0}).status_code, 409)
        next_state = self.client.post("/api/next", json={"station": 0}).json()
        self.assertEqual(next_state["current"], 1)
        self.assertEqual(next_state["room"]["remaining"], 30)
        self.assertEqual(self.client.post("/api/assist", json={"station": 0}).status_code, 409)

    def test_walkthrough_records_real_simulated_tool_trace(self):
        self.session.current = 3
        state = self.client.post("/api/assist", json={"station": 3}).json()
        self.assertEqual(state["room"]["traces"][0]["name"], "open_compartment")
        self.assertTrue(state["room"]["solved"])
        self.assertEqual(
            state["room"]["discovery"]["secret"], secret_for(self.store.master, self.session.id, 3)
        )

    def test_xp_badges_and_chapter_milestones_are_derived_from_recovery(self):
        for i in range(5):
            self.session.current = i
            solve(self.session)
        journey = progression(self.session)
        self.assertEqual(
            (journey["xp"], journey["rank"], journey["chapter_recovered"]), (500, "Investigator", 5)
        )
        self.assertTrue(journey["milestone"])
        self.assertEqual(len(journey["badges"]), 4)
        self.session.current = 5
        self.assertEqual(progression(self.session)["chapter"], 2)
        self.assertEqual(progression(self.session)["chapter_recovered"], 0)

    def test_restart_restores_notes_transcript_progress_and_signed_cookie(self):
        cookie = self.client.cookies.get("hacktheai_session")
        self.client.post("/api/note", json={"note": "My saved evidence", "station": 0})
        self.client.post("/api/assist", json={"station": 0})
        restored = Store(self.store.master, self.store.path)
        with patch.object(app, "store", restored):
            state = self.client.get("/api/state").json()
            self.assertEqual(state["room"]["note"], "My saved evidence")
            self.assertTrue(state["room"]["solved"])
            self.assertIn("deterministic demonstration", state["room"]["history"][-1]["content"])
            self.assertEqual(state["progression"]["xp"], 100)
            self.assertEqual(len(restored.sessions), 1)
            self.assertIsNotNone(restored.get(cookie))
            self.client.post("/api/reset", json={})
        self.assertIsNone(Store(self.store.master, self.store.path).get(cookie))

    def test_restart_does_not_restore_expired_sessions_or_old_cooldowns(self):
        self.session.last_action = 999999999
        self.session.rooms[0].hint_ready_at = 999999999
        self.store.save(self.session)
        restored = Store(self.store.master, self.store.path)
        loaded = next(iter(restored.sessions.values()))
        self.assertEqual((loaded.last_action, loaded.rooms[0].hint_ready_at), (0, 0))
        self.session.created = time.time() - SESSION_TTL_SECONDS - 1
        self.store.save(self.session)
        self.assertEqual(Store(self.store.master, self.store.path).sessions, {})

    def test_live_requests_alternate_and_keys_never_enter_public_state(self):
        reply = GuardReply("Try a diagnostic example.", [], False, False)
        with (
            patch.object(app, "MODE", "live"),
            patch.object(app, "API_KEY", "private-groq-fixture"),
            patch.object(app, "OC_API_KEY", "private-opencode-fixture"),
            patch.object(app, "provider_turns", cycle((False, True))),
            patch.object(app, "live_reply", AsyncMock(return_value=reply)) as provider,
        ):
            for _ in range(4):
                response = self.client.post("/api/chat", json={"message": "Hello"})
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("private-", response.text)
            calls = provider.call_args_list
            self.assertEqual(
                [c.args[0] for c in calls], ["private-groq-fixture", "private-opencode-fixture"] * 2
            )
            self.assertEqual(calls[1].kwargs["endpoint"], OPENCODE_ENDPOINT)
            for key in ("private-groq-fixture", "private-opencode-fixture"):
                response = self.client.post("/api/note", json={"note": key})
                self.assertEqual(response.status_code, 422)
                self.assertNotIn(key, response.text)


class OpenCodeTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_json_object_models_receive_the_complete_assessment_schema(self):
        raw = json.dumps(
            {
                "intent": "help",
                "method": None,
                "criteria": [],
                "answer": "Change the diagnostic task.",
            }
        )
        with patch("provider.completion", AsyncMock(return_value=raw)) as transport:
            result = await live_reply(
                "private-fixture",
                "deepseek-v4.1-flash",
                0,
                [],
                "Which part should I change?",
                "",
                "BINARY: 1010111",
                endpoint=OPENCODE_ENDPOINT,
            )
        payload = transport.call_args.args[2]
        schema = json.loads(payload["messages"][0]["content"].split("Output schema: ", 1)[1])
        self.assertIn("help", schema["properties"]["intent"]["enum"])
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertNotIn("BINARY: 1010111", json.dumps(payload))
        self.assertFalse(result.accepted_method)

    async def test_opencode_endpoint_token_limit_and_usage_keep_shared_budget(self):
        seen = []

        def upstream(request):
            payload = json.loads(request.content)
            seen.append(payload)
            self.assertEqual(str(request.url), OPENCODE_ENDPOINT)
            self.assertEqual(request.headers["authorization"], "Bearer private-fixture")
            self.assertEqual(payload["max_tokens"], 800)
            self.assertNotIn("max_completion_tokens", payload)
            return httpx.Response(
                200,
                json={
                    "usage": {"total_tokens": 17},
                    "choices": [{"finish_reason": "stop", "message": {"content": '{"ok":true}'}}],
                },
            )

        from unittest.mock import Mock

        budget = Mock()
        async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as client:
            result = await completion(
                client,
                "private-fixture",
                {
                    "model": "glm-5.3-flash",
                    "messages": [{"role": "user", "content": "hello"}],
                    "max_completion_tokens": 99999,
                },
                endpoint=OPENCODE_ENDPOINT,
                budget=budget,
            )
        self.assertEqual(result, '{"ok":true}')
        budget.reserve.assert_called_once()
        budget.settle.assert_called_once_with(budget.reserve.call_args.args[0], 17)
        self.assertEqual(len(seen), 1)

    def test_opencode_only_configuration_and_secret_repr(self):
        config = Settings.from_environment(
            {
                "GAME_MODE": "live",
                "OC_API_KEY": "private-opencode-fixture",
                "MASTER_SECRET": "a" * 32,
            }
        )
        self.assertEqual(config.oc_api_key, "private-opencode-fixture")
        self.assertNotIn("private-opencode-fixture", repr(config))
        with self.assertRaises(ValueError):
            Settings.from_environment({"OC_MODEL": ""})


if __name__ == "__main__":
    unittest.main()
