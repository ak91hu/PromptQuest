"""Validated server configuration and shared limits."""

import ipaddress
import os
from dataclasses import dataclass, field
from typing import Mapping
from urllib.parse import urlsplit

DEFAULT_MODEL = "openai/gpt-oss-120b"
SESSION_TTL_SECONDS = 6 * 60 * 60
MAX_SESSIONS = 500
ACTION_COOLDOWN_SECONDS = 0.8
HINT_COOLDOWN_SECONDS = 5
HISTORY_MESSAGES = 40
PROVIDER_HISTORY_MESSAGES = 12
TRACE_ENTRIES = 20


@dataclass(frozen=True)
class Settings:
    mode: str
    model: str
    port: int
    abuse_db_path: str
    trusted_proxy_cidrs: tuple
    provider_token_limit: int
    provider_daily_token_limit: int
    secure_cookies: bool
    api_key: str = field(repr=False)
    master_secret: str = field(repr=False)
    public_origins: tuple[str, ...] = ()

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if environment is None else environment
        mode = env.get("GAME_MODE", "demo").strip().lower()
        model = env.get("GROQ_MODEL", DEFAULT_MODEL).strip()
        api_key = env.get("GROQ_API_KEY", "").strip()
        master = env.get("MASTER_SECRET", "")
        public_origin = env.get("PUBLIC_ORIGIN", "").strip()
        origins = (
            (public_origin,)
            if public_origin
            else tuple(
                "https://" + host.strip()
                for host in env.get("NF_HOSTS", "").split(",")
                if host.strip()
            )
        )
        try:
            for origin in origins:
                parsed = urlsplit(origin)
                if (
                    parsed.scheme not in {"http", "https"}
                    or not parsed.hostname
                    or parsed.username is not None
                    or parsed.password is not None
                    or parsed.path not in {"", "/"}
                    or parsed.query
                    or parsed.fragment
                    or any(char.isspace() for char in origin)
                ):
                    raise ValueError
                # Accessing port also rejects malformed/out-of-range ports.
                parsed.port
        except ValueError:
            raise ValueError("Configure a valid PUBLIC_ORIGIN or Northflank NF_HOSTS.") from None
        if mode not in {"demo", "live"}:
            raise ValueError("GAME_MODE must be demo or live.")
        if not model:
            raise ValueError("GROQ_MODEL must not be empty.")
        if mode == "live" and (not api_key or len(master) < 32):
            raise ValueError(
                "Live mode requires GROQ_API_KEY and a MASTER_SECRET of at least 32 characters."
            )
        try:
            port = int(env.get("PORT", "10000"))
        except ValueError:
            raise ValueError("PORT must be an integer from 1 through 65535.") from None
        if not 1 <= port <= 65535:
            raise ValueError("PORT must be an integer from 1 through 65535.")
        try:
            trusted = tuple(
                ipaddress.ip_network(part.strip())
                for part in env.get("TRUSTED_PROXY_CIDRS", "").split(",")
                if part.strip()
            )
            if any(network.prefixlen == 0 for network in trusted):
                raise ValueError("Unrestricted proxy trust is forbidden.")
            token_limit = int(env.get("PROVIDER_TOKEN_LIMIT_PER_IP", "3000000"))
            daily_limit = int(env.get("PROVIDER_DAILY_TOKEN_LIMIT", "30000000"))
            if not 1000 <= daily_limit <= 1_000_000_000:
                raise ValueError("Invalid daily token budget.")
            if not 1000 <= token_limit <= 100_000_000:
                raise ValueError("Invalid token budget.")
        except ValueError:
            raise ValueError(
                "Configure explicit TRUSTED_PROXY_CIDRS, a per-IP token budget of 1000..100000000 and a daily budget of 1000..1000000000."
            ) from None
        return cls(
            mode=mode,
            model=model,
            port=port,
            api_key=api_key,
            master_secret=master,
            abuse_db_path=env.get("ABUSE_DB_PATH", ".data/abuse.sqlite3"),
            trusted_proxy_cidrs=trusted,
            provider_token_limit=token_limit,
            provider_daily_token_limit=daily_limit,
            secure_cookies=env.get("SECURE_COOKIES", "").lower() in {"1", "true", "yes"}
            or any(urlsplit(origin).scheme == "https" for origin in origins),
            public_origins=tuple(origin.rstrip("/") for origin in origins),
        )
