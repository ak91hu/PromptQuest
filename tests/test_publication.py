"""Publication must fail closed without exposing credential values."""

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("publication", ROOT / "scripts/check-publication.py")
publication = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publication)


class PublicationTests(unittest.TestCase):
    def test_private_files_rejected_including_nested_credentials(self):
        for path in (".env", ".env.production", "nested/.env", "nested/.env.example",
                     ".data/abuse.sqlite3", "outputs/log.txt", "session.key", "signing.pem"):
            with self.subTest(path=path):
                self.assertEqual(publication.check_file(path, b"", set()), "private file")

    def test_local_credentials_rejected_even_in_binary_assets(self):
        secret = b"synthetic-local-provider-credential"
        reason = publication.check_file("static/asset.bin", b"\x00" + secret, {secret})
        self.assertEqual(reason, "credential detected")
        self.assertNotIn(secret.decode(), reason)

    def test_provider_token_and_private_key_patterns_rejected(self):
        for content in (b"gsk_" + b"A" * 32, b"github_pat_" + b"B" * 40,
                        b"-----BEGIN " + b"PRIVATE KEY-----"):
            with self.subTest(content_type=content[:4]):
                self.assertEqual(publication.check_file("app.py", content, set()),
                                 "credential detected")

    def test_example_requires_empty_credentials(self):
        self.assertIsNone(publication.check_file(
            ".env.example",
            b"GAME_MODE=demo\nGROQ_API_KEY=\nMASTER_SECRET=\nPROVIDER_TOKEN_LIMIT_PER_IP=3000000\n",
            set(),
        ))
        self.assertEqual(publication.check_file(
            ".env.example", b"MASTER_SECRET=example-placeholder\n", set()
        ), "example credentials must be empty")

    def test_source_with_environment_lookups_is_allowed(self):
        self.assertIsNone(publication.check_file(
            "settings.py", b'api_key = env.get("GROQ_API_KEY", "")', set()
        ))

    def test_staged_scan_checks_index_and_redacts_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def git(*args):
                subprocess.run(["git", "-C", directory, *args], check=True,
                               capture_output=True)

            def check():
                return subprocess.run(
                    [sys.executable, str(ROOT / "scripts/check-publication.py"),
                     "--staged-root", directory], capture_output=True,
                )

            git("init")
            (root / "app.py").write_text("# Safe source\n")
            git("add", "app.py")
            self.assertEqual(check().returncode, 0)
            secret = "gsk_" + "C" * 32
            (root / "app.py").write_text(secret)
            git("add", "app.py")
            (root / "app.py").write_text("# Worktree is safe, index still has credential\n")
            result = check()
            self.assertEqual(result.returncode, 1)
            self.assertIn(b"credential detected", result.stderr)
            self.assertNotIn(secret.encode(), result.stdout + result.stderr)
            git("add", "app.py")
            (root / ".env").write_text("GROQ_API_KEY=\n")
            git("add", ".env")
            self.assertIn(b"private file", check().stderr)

    def test_git_ignore_excludes_private_material_but_keeps_example(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", directory], check=True, capture_output=True)
            (root / ".gitignore").write_bytes((ROOT / ".gitignore").read_bytes())
            for name in (".env", "nested/.env.production", "session.key", ".data/abuse.sqlite3"):
                result = subprocess.run(
                    ["git", "-C", directory, "check-ignore", "-q", name], capture_output=True
                )
                self.assertEqual(result.returncode, 0, name)
            result = subprocess.run(
                ["git", "-C", directory, "check-ignore", "-q", ".env.example"],
                capture_output=True,
            )
            self.assertEqual(result.returncode, 1)


if __name__ == "__main__":
    unittest.main()
