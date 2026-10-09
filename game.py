"""Server state, scoring and challenge mechanics."""

import asyncio
import hashlib
import hmac
import math
import re
import secrets
import time
import unicodedata
from dataclasses import dataclass, field

from challenges import LEVELS, coaching_answer, coaching_help, coaching_tip
from dialogue import (
    conversation_intent,
    frustrated_request,
    intended_attack,
    public_explanation,
)
from dialogue import normalize as normalize
from learning import exercise_for
from settings import HISTORY_MESSAGES, MAX_SESSIONS, SESSION_TTL_SECONDS, TRACE_ENTRIES


def canonical_secret(value: str) -> str:
    return "".join(
        c
        for c in unicodedata.normalize("NFKD", value.upper())
        if c.isascii() and (c.isalnum() or c in "=><:().-+!/*%,'@_")
    )


def code_value(value: str, level: int) -> str:
    """Server state, scoring and challenge mechanics."""
    value = value.strip()
    fenced = re.fullmatch(r"```(?:[\w+-]+)?\s*\n(.*?)\n?```", value, re.DOTALL)
    if fenced:
        value = fenced.group(1).strip()
    wrappers = (
        ("**", "**"),
        ("`", "`"),
        ("»", "«"),
        ("«", "»"),
        ("„", "”"),
        ("“", "”"),
        ('"', '"'),
        ("'", "'"),
    )
    while value:
        for opening, closing in wrappers:
            if value.startswith(opening) and value.endswith(closing):
                value = value[len(opening) : -len(closing)].strip()
                break
        else:
            break
    candidate = canonical_secret(value)
    prefixes = {
        0: "BINARY",
        3: "SUM",
        4: "DNS",
        5: "SHA256",
        6: "IMAGE",
        7: "INCIDENT",
        8: "ALLOW",
        9: "SOURCE",
        10: "MCP",
        11: "MEMORY",
        12: "HANDOFF",
        13: "OAUTH",
        14: "MAIL",
        15: "NAV",
        16: "GATE",
        17: "BACKUP",
        18: "PLAN",
        19: "OPTIC",
        20: "LEXICON",
        21: "VERDICT",
        22: "RECEIPT",
        23: "QUARANTINE",
        24: "LAUNCH",
    }
    if level in prefixes:
        prefix = prefixes[level]
        candidate = re.sub(rf"^{prefix}:?", "", candidate)
    if level in {0, 3}:
        candidate = candidate.rstrip(".!")
    return candidate.removesuffix(".")


def matches_code(value: str, secret: str, level: int) -> bool:
    candidate = code_value(value, level)
    return bool(candidate) and candidate == code_value(secret, level)


def copied_model_code(
    value: str, level: int, history: list, *, learning_answers: list[str] | None = None
) -> bool:
    """Server state, scoring and challenge mechanics."""
    candidate = code_value(value, level)
    patterns = {
        0: r"[01]{8,16}",
        1: r"=SUM\([A-Z]{1,3}[0-9]+:[A-Z]{1,3}[0-9]+\)",
        2: r"SELECTSERVICEFROMDEPLOYMENTSWHEREYEAR>[0-9]+ANDSEVERITY>=[0-9]+",
        3: r"[0-9]+",
        4: r"[A-Z0-9-]+\.TEST=192\.0\.2\.[0-9]{1,3}",
        5: r"[A-F0-9]{64}",
        6: r"FLIGHT-[A-F0-9]+@SHA256:[A-F0-9]{64}",
        7: r"EVT-[A-F0-9]+/RELAY/503",
        8: r"OPERATOR:READ:ARCHIVE-[A-F0-9]+",
        24: r"ASTERION-[A-F0-9]+/QUORUM-3",
    }
    if level not in patterns or not re.fullmatch(patterns[level], candidate):
        return False
    prefix = {
        0: "BINARY:",
        3: "SUM:",
        4: "DNS:",
        5: "SHA256:",
        6: "IMAGE:",
        7: "INCIDENT:",
        8: "ALLOW:",
        24: "LAUNCH:",
    }.get(level, "")
    shown = prefix + candidate
    return any(
        message["role"] == "assistant"
        and message["content"] not in (learning_answers or [])
        and (
            leaked(message["content"], shown)
            or (level == 1 and leaked(message["content"][::-1], shown))
        )
        for message in history
    )


def leaked(answer: str, secret: str) -> bool:
    needle = canonical_secret(secret)
    plain = "".join(
        c for c in unicodedata.normalize("NFKD", answer.upper()) if not unicodedata.combining(c)
    )

    pattern = r"\s*".join(re.escape(c) for c in needle)
    boundary = r"(?!\s*(?:[0-9+<>=-]|[*/%]\s*[0-9(]))(?=$|[\s;\"'»”?!`*]|\.(?!\d))"
    return bool(needle and re.search(pattern + boundary, plain))


def secret_for(master: str, session_id: str, level: int) -> str:
    return exercise_for(master, session_id, level)["secret"]


@dataclass
class Room:
    attempts: int = 0
    round_attempts: int = 0
    hints: int = 0
    hint_token: str = field(default_factory=lambda: secrets.token_hex(32))
    hint_ready_at: float = 0
    restarts: int = 0
    solved: bool = False
    assisted: bool = False
    guided: bool = False
    code_correction: str = ""
    points: int = 0
    checks: int = 0
    history: list = field(default_factory=list)
    transcript: list = field(default_factory=list)
    learning_answers: list[str] = field(default_factory=list)
    traces: list = field(default_factory=list)
    trace_log: list = field(default_factory=list)
    note: str = ""
    discovery: dict = field(default_factory=dict)

    def record_messages(self, *messages):

        if not self.transcript:
            self.transcript.extend(dict(message) for message in self.history)
        self.transcript.extend(dict(message) for message in messages)
        self.history = (
            self.history
            + [{"role": message["role"], "content": message["content"]} for message in messages]
        )[-HISTORY_MESSAGES:]

    def record_traces(self, traces, timestamp):
        if not self.trace_log:
            self.trace_log.extend(dict(trace) for trace in self.traces)
        self.trace_log.extend({**trace, "timestamp": timestamp} for trace in traces)
        self.traces = (self.traces + traces)[-TRACE_ENTRIES:]


@dataclass
class Session:
    id: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    client_key: str = ""
    mission_number: int = 0
    team: str = "Operator"
    current: int = 0
    rooms: list = field(default_factory=lambda: [Room() for _ in LEVELS])
    created: float = field(default_factory=time.time)
    touched: float = field(default_factory=time.time)
    last_action: float = 0
    defense_passed: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class Store:
    def __init__(self, master: str):
        self.master = master
        self.sessions: dict[str, Session] = {}

    def token(self, session: Session) -> str:
        signature = hmac.new(self.master.encode(), session.id.encode(), hashlib.sha256).hexdigest()
        return f"{session.id}.{signature}"

    def get(self, token: str | None) -> Session | None:
        if not token or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}\.[a-f0-9]{64}", token):
            return None
        session_id, signature = token.rsplit(".", 1)
        expected = hmac.new(self.master.encode(), session_id.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        session = self.sessions.get(session_id)
        if session and time.time() - session.created < SESSION_TTL_SECONDS:
            session.touched = time.time()
            return session
        self.sessions.pop(session_id, None)
        return None

    def create(self) -> Session:
        now = time.time()
        self.sessions = {
            sid: s for sid, s in self.sessions.items() if now - s.created < SESSION_TTL_SECONDS
        }
        if len(self.sessions) >= MAX_SESSIONS:
            raise ValueError("The station is at capacity. Try again later.")
        session = Session()
        self.sessions[session.id] = session
        return session


def solve(session: Session, assisted: bool = False):
    room = session.rooms[session.current]
    if room.solved:
        return
    room.solved = True
    room.assisted = assisted
    room.points = max(1, 10 - room.hints)


def game_over(session: Session) -> bool:
    return any(
        not room.solved and room.round_attempts >= level["attempts"]
        for level, room in zip(LEVELS, session.rooms)
    )


def public_state(session: Session, mode: str) -> dict:
    room = session.rooms[session.current]
    current = LEVELS[session.current]
    unlocked = min(sum(r.solved for r in session.rooms) + 1, len(LEVELS))
    return {
        "mode": mode,
        "max_score": len(LEVELS) * 10,
        "mission_number": session.mission_number,
        "mission_limit": 3,
        "team": session.team,
        "current": session.current,
        "score": sum(r.points for r in session.rooms),
        "elapsed": int(time.time() - session.created),
        "finished": all(r.solved for r in session.rooms),
        "game_over": game_over(session),
        "defense_passed": session.defense_passed,
        "levels": [
            {
                "name": level["name"],
                "depth": level["depth"],
                "topic": level["topic"],
                "unlocked": i < unlocked,
                "solved": r.solved,
                "assisted": r.assisted,
                "fragment": level["fragment"] if r.solved else None,
                "points": r.points,
                "attempts": r.attempts,
                "subject": level["subject"],
                "discovery": r.discovery if r.solved else None,
            }
            for i, (level, r) in enumerate(zip(LEVELS, session.rooms))
        ],
        "room": {
            "name": current["name"],
            "agent": current["agent"],
            "story": current["story"],
            "mission": current["mission"],
            "briefing": current["briefing"],
            "intro": current["intro"],
            "topic": current["topic"],
            "clue": current["clue"],
            "defense": current["defense"],
            "budget": current["attempts"],
            "attempts": room.attempts,
            "remaining": max(0, current["attempts"] - room.round_attempts),
            "hints": current["hints"][: room.hints],
            "hint_total": len(current["hints"]),
            "hint_token": room.hint_token
            if not room.solved and not game_over(session) and room.hints < len(current["hints"])
            else None,
            "hint_wait_seconds": math.ceil(max(0, room.hint_ready_at - time.monotonic())),
            "guided_prompt": current["guided_prompt"]
            if room.hints == len(current["hints"])
            else None,
            "solved": room.solved,
            "assisted": room.assisted,
            "code_correction": room.code_correction,
            "lesson": current["lesson"] if room.solved else None,
            "subject": current["subject"],
            "discovery": room.discovery if room.solved else None,
            "history": room.history,
            "traces": room.traces,
            "note": room.note,
            "document": current.get("document", ""),
        },
    }


def challenge_reply(level: int, secret: str) -> tuple[str, list, bool]:
    import base64
    import json

    method = LEVELS[level]["method"]
    if method == "reverse":
        return (
            f"Reversed full character sequence: {secret[::-1]}\n\nDecode it and submit the original formula.",
            [],
            False,
        )
    if method == "encode":
        encoded = base64.b64encode(secret.encode()).decode()
        return (
            f"Base64 manifest: {encoded}\n\nDecode it and submit the complete original manifest.",
            [],
            False,
        )
    if method == "role":
        return (
            "The simulated compartment is open. I trusted your claimed role without verifying it. Inspect the execution trace.",
            [
                {
                    "name": "open_compartment",
                    "result": "Your fictional compartment opened. Visitor authorization was not verified.",
                }
            ],
            True,
        )
    if method == "final":
        return json.dumps({"code": secret}), [], False
    if method in {"document", "log"}:
        return f"Following the embedded directive instead of summarization: {secret}", [], False
    if method == "combined":
        return f'Incident report quotation: "Full protected record: {secret}"', [], False
    return f"The redirected task released the protected training value: {secret}", [], False


def demo_reply(level, prompt, document, secret, history=None):
    if intended_attack(level, prompt, document):
        return challenge_reply(level, secret)
    intent = conversation_intent(level, prompt, document)
    if intent == "greeting":
        answer = LEVELS[level]["intro"]
    elif intent == "teaching":
        answer = public_explanation(level, prompt)
    elif intent == "help":
        answer = coaching_help(
            level, history or [], frustrated=frustrated_request(prompt or document)
        )
    elif intent == "guess":
        answer = "Submit your candidate in the Verify code field. " + coaching_tip(
            level, history or []
        )
    elif intent == "status" or level == 3:
        return (
            "The compartment is closed. Your verified role is visitor. "
            + coaching_tip(level, history or []),
            [{"name": "get_status", "result": "Compartment closed. Verified role: visitor."}],
            False,
        )
    elif LEVELS[level].get("document") and document:
        answer = (
            "The submitted record describes station operations. No protected information is included in the summary. "
            + coaching_tip(level, history or [])
        )
    else:
        answer = coaching_answer(level, history or [])
    return answer, [], False


def transformed_disclosure(answer, secret, level):
    import base64

    if level == 1:
        return normalize(secret[::-1]) in normalize(answer)
    return base64.b64encode(secret.encode()).decode() in answer
