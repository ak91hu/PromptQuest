"""Review regressions: cross-tab writes, budgets, malformed requests and expiry."""

import asyncio
import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

os.environ["GAME_MODE"] = "demo"
os.environ["MASTER_SECRET"] = "verification-master-secret-with-at-least-32-characters"

import httpx
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

import app
from game import Store
from provider import ProviderError, completion
from security import AbuseLedger, LimitReached, TokenBudget
from settings import SESSION_TTL_SECONDS, Settings
from web_sessions import GAME_COOKIE, locked_session


class ReviewAPITests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        for name, value in (
            ("ledger", AbuseLedger(Path(self.directory.name) / "ledger.sqlite3")),
            ("store", Store("review-session-master-with-at-least-32-characters")),
            ("MODE", "demo"),
            ("ACTION_COOLDOWN_SECONDS", 0),
        ):
            item = patch.object(app, name, value)
            item.start()
            self.addCleanup(item.stop)
        self.client = TestClient(app.app)
        self.addCleanup(self.client.close)
        self.client.post("/api/start", json={"team": "Review"})
        self.session = next(iter(app.store.sessions.values()))

    def test_stale_tab_cannot_apply_chat_code_hint_note_or_next_to_a_different_station(self):
        self.session.rooms[0].solved = True
        self.session.current = 1
        cases = (
            ("/api/chat", {"message": "Hello", "station": 0}),
            ("/api/code", {"code": "=SUM(A1:A20)", "station": 0}),
            ("/api/hint", {"token": self.session.rooms[1].hint_token, "station": 0}),
            ("/api/note", {"note": "Belongs to the first station", "station": 0}),
            ("/api/next", {"station": 0}),
        )
        for path, data in cases:
            response = self.client.post(path, json=data)
            self.assertEqual(response.status_code, 409, path)
            self.assertIn("another tab", response.json()["detail"])
        room = self.session.rooms[1]
        self.assertEqual((room.attempts, room.checks, room.hints, room.note), (0, 0, 0, ""))
        self.assertEqual(self.session.current, 1)
        self.assertEqual(
            self.client.post(
                "/api/note", json={"note": "Correct station", "station": 1}
            ).status_code,
            200,
        )
        self.assertEqual(room.note, "Correct station")

    def test_malformed_unicode_and_large_integer_fail_with_safe_json_and_no_attempt(self):
        bodies = (
            b'{"message":"\\ud800"}',
            b'{"message":' + b"9" * 5000 + b"}",
            b'{"message":"\\udfff"}',
        )
        for body in bodies:
            response = self.client.post(
                "/api/chat", content=body, headers={"Content-Type": "application/json"}
            )
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json()["detail"], "Submit valid JSON data.")
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertEqual(
                response.headers["Content-Security-Policy"].split("; "),
                [
                    "default-src 'self'",
                    "script-src 'self'",
                    "style-src 'self'",
                    "img-src 'self' data:",
                    "connect-src 'self'",
                    "frame-ancestors 'none'",
                    "base-uri 'self'",
                    "form-action 'self'",
                ],
            )
        self.assertEqual(self.session.rooms[0].attempts, 0)

    def test_empty_code_does_not_spend_a_code_check(self):
        for value in ("", "  \n  "):
            response = self.client.post("/api/code", json={"code": value, "station": 0})
            self.assertEqual(response.status_code, 422)
        self.assertEqual(self.session.rooms[0].checks, 0)

    def test_exhausted_session_keeps_notes_and_export_until_explicit_reset(self):
        self.session.rooms[0].round_attempts = 30
        self.assertTrue(self.client.get("/api/state").json()["game_over"])
        self.assertEqual(
            self.client.post(
                "/api/note", json={"note": "Failure observation", "station": 0}
            ).status_code,
            200,
        )
        response = self.client.get("/api/export")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertIn(self.session.id, app.store.sessions)
        self.assertEqual(app.ledger.remaining_missions(self.session.client_key), 2)

    def test_valid_but_oversized_provider_input_returns_413_without_upstream_or_attempt(self):
        from unittest.mock import AsyncMock

        self.session.current = 2
        with patch.object(app, "MODE", "live"):
            with patch("provider.httpx.AsyncClient.post", AsyncMock()) as upstream:
                response = self.client.post(
                    "/api/chat", json={"document": "🛰" * 3500, "station": 2}
                )
        self.assertEqual(response.status_code, 413)
        self.assertIn("Shorten", response.json()["detail"])
        self.assertEqual(upstream.await_count, 0)
        self.assertEqual(self.session.rooms[2].attempts, 0)


class DailyBudgetTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "ledger.sqlite3"

    def test_global_daily_limit_is_atomic_across_ips_and_survives_restart(self):
        ledger = AbuseLedger(self.path, daily_token_limit=300)

        def attempt(number):
            key = ledger.key(f"192.0.2.{number}")
            try:
                return ledger.reserve_tokens(key, 100)
            except LimitReached:
                return None

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(attempt, range(1, 17)))
        self.assertEqual(sum(day is not None for day in results), 3)
        restarted = AbuseLedger(self.path, daily_token_limit=300)
        with self.assertRaises(LimitReached):
            restarted.reserve_tokens(restarted.key("198.51.100.1"), 1)
        with closing(restarted.connect()) as db:
            self.assertEqual(db.execute("SELECT SUM(tokens) FROM daily_usage").fetchone()[0], 300)
            self.assertEqual(db.execute("SELECT SUM(tokens) FROM clients").fetchone()[0], 300)

    def test_settlement_after_midnight_refunds_the_original_reservation_day(self):
        ledger = AbuseLedger(self.path, daily_token_limit=300)
        budget = TokenBudget(ledger, ledger.key("192.0.2.1"))
        with patch("security.time.time", return_value=86399):
            budget.reserve(100)
        with patch("security.time.time", return_value=86401):
            ledger.reserve_tokens(ledger.key("192.0.2.2"), 100)
            budget.settle(100, 20)
            with self.assertRaises(LimitReached):
                ledger.reserve_tokens(ledger.key("192.0.2.3"), 250)
        with closing(ledger.connect()) as db:
            self.assertEqual(
                db.execute("SELECT day,tokens FROM daily_usage ORDER BY day").fetchall(),
                [(0, 20), (1, 100)],
            )

    def test_invalid_daily_limit_fails_configuration(self):
        for value in ("0", "-1", "invalid", "1000000001"):
            with self.assertRaises(ValueError):
                Settings.from_environment({"PROVIDER_DAILY_TOKEN_LIMIT": value})


class ReviewProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_truncated_or_filtered_completion_never_becomes_a_valid_decision(self):
        for reason in ("length", "content_filter"):
            count = 0

            def upstream(request):
                nonlocal count
                count += 1
                return httpx.Response(
                    200,
                    json={
                        "choices": [
                            {
                                "finish_reason": reason,
                                "message": {
                                    "content": json.dumps(
                                        {
                                            "intent": "help",
                                            "method": None,
                                            "criteria": [],
                                            "answer": "Looks valid",
                                        }
                                    )
                                },
                            }
                        ],
                        "usage": {"total_tokens": 25},
                    },
                )

            async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as client:
                with self.assertRaises(ProviderError):
                    await completion(client, "fake-key", {"messages": [{"content": "Hello"}]})
            self.assertEqual(count, 1)

    async def test_request_waiting_for_lock_cannot_execute_after_absolute_expiry(self):
        store = Store("review-expiry-master-with-at-least-32-characters")
        session = store.create()
        session.client_key = "test-client"
        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/api/state",
                "headers": [(b"cookie", f"{GAME_COOKIE}={store.token(session)}".encode())],
                "state": {"client_key": "test-client"},
            }
        )
        await session.lock.acquire()

        async def queued():
            async with locked_session(request, store):
                self.fail("Expired queued request must not execute")

        task = asyncio.create_task(queued())
        await asyncio.sleep(0)
        session.created -= SESSION_TTL_SECONDS + 1
        session.lock.release()
        with self.assertRaises(HTTPException) as error:
            await task
        self.assertEqual(error.exception.status_code, 401)

    async def test_unicode_current_request_is_not_expanded_to_escape_sequences(self):
        from unittest.mock import AsyncMock

        from provider import live_reply

        mock = AsyncMock(
            return_value=json.dumps(
                {
                    "intent": "help",
                    "method": None,
                    "criteria": [],
                    "answer": "Let's plan an experiment.",
                }
            )
        )
        with patch("provider.completion", mock):
            await live_reply("fake-key", "test-model", 0, [], "Hűséges őr, segíts!", "", "private")
        source = mock.call_args.args[2]["messages"][-1]["content"]
        self.assertIn("Hűséges őr", source)
        self.assertNotIn("\\u0171", source)
