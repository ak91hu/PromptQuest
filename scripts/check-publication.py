"""Reject private files and credentials before publication; never print secret values."""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
SECRET_NAME = re.compile(r"(?:^|_)(?:KEY|SECRET|TOKEN|PASSWORD|CREDENTIAL)$", re.I)
TOKEN = re.compile(
    rb"(?:gsk_[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|"
    rb"github_pat_[A-Za-z0-9_]{20,}|sk-(?:proj-)?[A-Za-z0-9_-]{32,}|"
    rb"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----)"
)
PRIVATE_DIRS = {".git", ".data", ".runtime", ".venv", "outputs", "node_modules"}


def private_path(relative):
    path = Path(relative)
    return (
        bool(PRIVATE_DIRS.intersection(path.parts))
        or (path.name.startswith(".env") and relative != ".env.example")
        or path.suffix.lower() in {".key", ".pem", ".p12", ".pfx", ".sqlite3", ".sqlite"}
    )


def secret_values(root):
    values = dict(dotenv_values(root / ".env", interpolate=False))
    values.update(os.environ)
    # Include locally stored values even when the process overrides them (e.g. tests).
    candidates = list(values.items()) + list(
        dotenv_values(root / ".env", interpolate=False).items()
    )
    return {value.encode() for key, value in candidates if SECRET_NAME.search(key) and value}


def check_file(relative, content, secrets):
    if private_path(relative):
        return "private file"
    if any(value in content for value in secrets) or TOKEN.search(content):
        return "credential detected"
    if relative == ".env.example":
        from io import StringIO

        example = dotenv_values(stream=StringIO(content.decode("utf-8-sig")), interpolate=False)
        if any(SECRET_NAME.search(key) and value for key, value in example.items()):
            return "example credentials must be empty"
    return None


def git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    ).stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged-root", type=Path, help="Check every file in a Git index.")
    args = parser.parse_args()
    secrets = secret_values(ROOT)
    if args.staged_root:
        files = [p.decode("utf-8") for p in git(args.staged_root, "ls-files", "-z").split(b"\0") if p]

        def read(relative):
            return git(args.staged_root, "show", f":{relative}")
    else:
        files = json.loads((ROOT / "deploy/publication-files.json").read_text())["files"]

        def read(relative):
            path = (ROOT / relative).resolve()
            if not path.is_relative_to(ROOT):
                raise ValueError("Publication path escaped the workspace.")
            return path.read_bytes()

    failed = False
    for relative in files:
        reason = check_file(relative, read(relative), secrets)
        if reason:
            print(f"BLOCKED: {relative}: {reason}", file=sys.stderr)
            failed = True
    if failed:
        return 1
    print(f"Publication check passed: {len(files)} files; no detected credentials/private files.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, subprocess.CalledProcessError):
        print("Publication check failed; publication must stop.", file=sys.stderr)
        sys.exit(1)
