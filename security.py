"""Persistent admission and provider spending limits. IPs are stored only as keyed hashes."""

import hashlib
import hmac
import ipaddress
import os
import secrets
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from fastapi import HTTPException, Request

MISSION_LIMIT = 3
MAX_BODY_BYTES = 32768
MAX_PROVIDER_INPUT_BYTES = 12000
MAX_PROVIDER_OUTPUT_TOKENS = 800
PROVIDER_CALLS_PER_MINUTE = 12


class LimitReached(Exception):
    pass


def persistent_secret(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        value = path.read_text(encoding="ascii").strip()
        if len(value) < 32:
            raise ValueError("The persisted security key is invalid. Restore it before startup.")
        return value
    value = secrets.token_urlsafe(48)
    with os.fdopen(fd, "w", encoding="ascii") as stream:
        stream.write(value)
    return value


def normalize_ip(value):
    address = ipaddress.ip_address(value.strip())
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return address


def client_address(request: Request, trusted_proxies):
    if not request.client:
        raise HTTPException(400, "The client address is unavailable.")
    try:
        peer = normalize_ip(request.client.host)
    except ValueError:
        # Test transports use this literal; real socket transports always provide IPs.
        if request.client.host == "testclient":
            peer = normalize_ip("192.0.2.1")
        else:
            raise HTTPException(400, "The client address is invalid.") from None

    def trusted(ip):
        return any(ip in network for network in trusted_proxies)

    forwarded = request.headers.get("x-forwarded-for")
    if not trusted(peer) or not forwarded:
        return str(peer)
    if len(forwarded) > 512:
        raise HTTPException(400, "The forwarded address chain is invalid.")
    try:
        chain = [normalize_ip(part) for part in forwarded.split(",")]
    except ValueError:
        raise HTTPException(400, "The forwarded address chain is invalid.") from None
    # Skip only explicitly trusted hops, from the socket peer towards the original client.
    for address in reversed(chain):
        if not trusted(peer):
            break
        peer = address
    return str(peer)


def trusted_proxy_peer(request, networks):
    try:
        peer = normalize_ip(request.client.host)
        return any(peer in network for network in networks)
    except (ValueError, AttributeError):
        return False


class AbuseLedger:
    def __init__(self, path, token_limit=3_000_000, daily_token_limit=30_000_000):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.pepper = persistent_secret(self.path.with_suffix(".key"))
        self.token_limit = token_limit
        self.daily_token_limit = daily_token_limit
        with closing(self.connect()) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS clients (
                client_key TEXT PRIMARY KEY,
                missions INTEGER NOT NULL DEFAULT 0,
                tokens INTEGER NOT NULL DEFAULT 0,
                call_window INTEGER NOT NULL DEFAULT 0,
                calls INTEGER NOT NULL DEFAULT 0
            )""")

            db.execute("""CREATE TABLE IF NOT EXISTS daily_usage (
                day INTEGER PRIMARY KEY,
                tokens INTEGER NOT NULL DEFAULT 0
            )""")

    def connect(self):
        return sqlite3.connect(self.path, timeout=5, isolation_level=None)

    def key(self, address):
        return hmac.new(
            self.pepper.encode(), ("client-ip:" + address).encode(), hashlib.sha256
        ).hexdigest()

    def claim_mission(self, client_key):
        with closing(self.connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                db.execute("INSERT OR IGNORE INTO clients(client_key) VALUES (?)", (client_key,))
                used = db.execute(
                    "SELECT missions FROM clients WHERE client_key=?", (client_key,)
                ).fetchone()[0]
                if used >= MISSION_LIMIT:
                    raise LimitReached(
                        "This network has used all three mission starts. Existing missions can still be continued."
                    )
                db.execute(
                    "UPDATE clients SET missions=missions+1 WHERE client_key=?", (client_key,)
                )
                db.commit()
                return used + 1
            except Exception:
                db.rollback()
                raise

    def reserve_tokens(self, client_key, amount):
        now = int(time.time())
        window, day = now // 60, now // 86400
        with closing(self.connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                db.execute("INSERT OR IGNORE INTO clients(client_key) VALUES (?)", (client_key,))
                tokens, previous_window, calls = db.execute(
                    "SELECT tokens,call_window,calls FROM clients WHERE client_key=?", (client_key,)
                ).fetchone()
                calls = calls if previous_window == window else 0
                if calls >= PROVIDER_CALLS_PER_MINUTE:
                    raise LimitReached(
                        "The AI request rate for this network is exhausted. Wait a minute. No prompt was consumed."
                    )
                if tokens + amount > self.token_limit:
                    raise LimitReached(
                        "The AI request allowance for this network is exhausted. Guided training remains available. No prompt was consumed."
                    )
                db.execute("INSERT OR IGNORE INTO daily_usage(day) VALUES (?)", (day,))
                total = db.execute("SELECT tokens FROM daily_usage WHERE day=?", (day,)).fetchone()[
                    0
                ]
                if total + amount > self.daily_token_limit:
                    raise LimitReached(
                        "The daily AI allowance is exhausted. Try again after 00:00 UTC or use guided training. No prompt was consumed."
                    )
                db.execute("UPDATE daily_usage SET tokens=tokens+? WHERE day=?", (amount, day))
                db.execute(
                    "UPDATE clients SET tokens=tokens+?,call_window=?,calls=? WHERE client_key=?",
                    (amount, window, calls + 1, client_key),
                )
                db.commit()
                return day
            except Exception:
                db.rollback()
                raise

    def settle_tokens(self, client_key, reserved, used, *, day=None):
        used = (
            used
            if isinstance(used, int) and not isinstance(used, bool) and 0 <= used <= reserved
            else reserved
        )
        day = int(time.time()) // 86400 if day is None else day
        with closing(self.connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                db.execute(
                    "UPDATE clients SET tokens=tokens-?+? WHERE client_key=?",
                    (reserved, used, client_key),
                )
                db.execute(
                    "UPDATE daily_usage SET tokens=tokens-?+? WHERE day=?",
                    (reserved, used, day),
                )
                db.commit()
            except Exception:
                db.rollback()
                raise

    def remaining_missions(self, client_key):
        with closing(self.connect()) as db:
            row = db.execute(
                "SELECT missions FROM clients WHERE client_key=?", (client_key,)
            ).fetchone()
            return max(0, MISSION_LIMIT - (row[0] if row else 0))


class TokenBudget:
    def __init__(self, ledger, client_key):
        self.ledger, self.client_key = ledger, client_key
        self.reservation_day = None

    def reserve(self, amount):
        self.reservation_day = self.ledger.reserve_tokens(self.client_key, amount)

    def settle(self, reserved, used):
        self.ledger.settle_tokens(self.client_key, reserved, used, day=self.reservation_day)
