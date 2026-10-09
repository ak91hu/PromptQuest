"""Deployment regressions: persistence, fail-closed proxy setup, and secret handling."""
import copy
import importlib.util
import json
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "northflank_prepare", ROOT / "scripts" / "prepare-northflank.py"
)
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class NorthflankPreparationTests(unittest.TestCase):
    def setUp(self):
        self.template = json.loads((ROOT / "northflank.json").read_text(encoding="utf-8"))
        self.environment = {
            "NORTHFLANK_API_TOKEN": "private-test-platform-token",
            "GROQ_API_KEY": "private-test-provider-key",
            "MASTER_SECRET": "private-test-master-" + "x" * 32,
        }

    def test_template_keeps_persistence_and_spending_guards(self):
        prepare.validate(self.template)
        inner = self.template["spec"]["spec"]["steps"][1]["spec"]["steps"]
        self.assertEqual(inner[2]["spec"]["attachedObjects"][0]["id"],
                         "$" + "{refs.service.id}")
        for node in (inner[1], inner[3]):
            env = node["spec"]["runtimeEnvironment"]
            self.assertEqual(env["PROVIDER_DAILY_TOKEN_LIMIT"],
                             "$" + "{args.PROVIDER_DAILY_TOKEN_LIMIT}")
            self.assertNotIn("GROQ_API_KEY", env)

    def test_ready_requires_explicit_proxy_configuration(self):
        self.template["arguments"]["TRUSTED_PROXY_CIDRS"] = ""
        with self.assertRaisesRegex(ValueError, "verified"):
            prepare.validate(self.template, ready=True)
        self.template["arguments"]["TRUSTED_PROXY_CIDRS"] = "192.0.2.4/32"
        prepare.validate(self.template, ready=True)

    def test_proxy_wildcards_and_invalid_networks_rejected(self):
        for value in ("0.0.0.0/0", "::/0", "192.0.2.3/24", "not-a-network", ""):
            with self.subTest(value=value), self.assertRaises(ValueError):
                prepare.validate_proxies(value)

    def test_repository_url_cannot_embed_credentials_or_use_wrong_host(self):
        for url in ("http://github.com/ak91hu/PromptQuest",
                    "https://github.com.evil.test/ak91hu/PromptQuest",
                    "https://user:secret@github.com/ak91hu/PromptQuest",
                    "https://github.com/ak91hu/PromptQuest?token=secret"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                prepare.validate_repository(url, "github")

    def test_automatic_run_and_public_secrets_rejected(self):
        for mutation in ("autorun", "public-key", "overrides"):
            template = copy.deepcopy(self.template)
            if mutation == "autorun":
                template["options"]["autorun"] = True
            elif mutation == "public-key":
                template["arguments"]["GROQ_API_KEY"] = "private"
            else:
                template["argumentOverrides"] = {"GROQ_API_KEY": "private"}
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                prepare.validate(template)

    def test_registration_sends_private_overrides_without_mutating_public_template(self):
        original = copy.deepcopy(self.template)
        response = BytesIO(b'{"data":{"id":"asterion-template"}}')
        with patch.object(prepare, "urlopen", return_value=response) as transport:
            identifier = prepare.save_template(self.template, self.environment, "my-team")
        request = transport.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(identifier, "asterion-template")
        self.assertEqual(request.full_url,
                         "https://api.northflank.com/v1/teams/my-team/templates")
        self.assertFalse(payload["options"]["runOnCreation"])
        self.assertFalse(payload["options"]["autorun"])
        self.assertEqual(payload["argumentOverrides"]["GROQ_API_KEY"],
                         self.environment["GROQ_API_KEY"])
        self.assertEqual(self.template, original)
        self.assertNotIn("private-test", json.dumps(self.template))

    def test_registration_error_does_not_echo_response_body(self):
        error = HTTPError("https://api.northflank.com/v1/templates", 400, "Bad", {},
                          BytesIO(b"private-test-provider-key"))
        with patch.object(prepare, "urlopen", side_effect=error):
            with self.assertRaises(ValueError) as result:
                prepare.save_template(self.template, self.environment)
        self.assertIn("HTTP 400", str(result.exception))
        self.assertNotIn("private-test", str(result.exception))

    def test_uncertain_registration_does_not_retry(self):
        with patch.object(prepare, "urlopen", side_effect=URLError("offline")) as transport:
            with self.assertRaisesRegex(ValueError, "before retrying"):
                prepare.save_template(self.template, self.environment)
        self.assertEqual(transport.call_count, 1)


if __name__ == "__main__":
    unittest.main()
