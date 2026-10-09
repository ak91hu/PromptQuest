"""HackTheAI - orbital AI security mission."""

import asyncio
import json
import secrets
import time
from pathlib import Path
from urllib.parse import urlsplit

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from certificate_pdf import render_certificate
from challenges import DEFENSES, LEVELS
from dialogue import conversation_intent, intended_attack
from game import (
    Store,
    copied_model_code,
    demo_reply,
    game_over,
    leaked,
    matches_code,
    public_state,
    secret_for,
    solve,
    transformed_disclosure,
)
from learning import exercise_for
from mission_pdf import make_report, render_pdf
from provider import ProviderError, live_reply
from schemas import Chat, Code, Defense, Hint, Note, Start, StationAction
from security import (
    MAX_BODY_BYTES,
    AbuseLedger,
    LimitReached,
    TokenBudget,
    client_address,
    persistent_secret,
    trusted_proxy_peer,
)
from settings import (
    ACTION_COOLDOWN_SECONDS,
    HINT_COOLDOWN_SECONDS,
    Settings,
)
from tutorial_routes import create_tutorial_router
from web_sessions import GAME_COOKIE, locked_session, set_session_cookie

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
settings = Settings.from_environment()
MODE = settings.mode
API_KEY = settings.api_key
MASTER = settings.master_secret
MODEL = settings.model
ledger = AbuseLedger(
    ROOT / settings.abuse_db_path,
    settings.provider_token_limit,
    settings.provider_daily_token_limit,
)
store = Store(MASTER or persistent_secret(ledger.path.with_name("session.key")))
tutorial_store = Store(secrets.token_urlsafe(48))
provider_slots = asyncio.Semaphore(6)


app = FastAPI(title="HackTheAI", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


app.include_router(create_tutorial_router(lambda: tutorial_store))


def mission_state(session):
    result = public_state(session, MODE)
    result["mission_starts_remaining"] = ledger.remaining_missions(session.client_key)
    return result


def request_station(data, session):
    if data is not None and data.station is not None and data.station != session.current:
        raise HTTPException(
            409, "This station changed in another tab. Reload to continue; no action was applied."
        )


def playable(session):
    if game_over(session):
        raise HTTPException(
            409, "Mission terminated. All 30 attempts have been used. Start a new mission."
        )
    room = session.rooms[session.current]
    if room.solved:
        raise HTTPException(409, "This station is recovered. Proceed to the next station.")
    return room


def throttle(session):
    if time.monotonic() - session.last_action < ACTION_COOLDOWN_SECONDS:
        raise HTTPException(429, "Wait a moment before your next experiment.")
    session.last_action = time.monotonic()


def complete(session, assisted=False):
    solve(session, assisted)
    session.rooms[session.current].discovery = exercise_for(
        store.master, session.id, session.current
    )


@app.exception_handler(RequestValidationError)
async def invalid_input(request, exc):
    return JSONResponse(
        {"detail": "The submitted data is invalid or too long. Check the fields."},
        status_code=422,
    )


def same_origin(origin: str, target: str) -> bool:
    try:
        source = urlsplit(origin)
        destination = urlsplit(target)

        def identity(url):
            return (url.scheme, url.hostname, url.port or (443 if url.scheme == "https" else 80))

        return (
            source.scheme in {"http", "https"}
            and source.username is None
            and not source.query
            and not source.fragment
            and source.path in {"", "/"}
            and identity(source) == identity(destination)
        )
    except ValueError:
        return False


@app.middleware("http")
async def headers_and_origin(request: Request, call_next):
    try:
        request.state.client_key = ledger.key(client_address(request, settings.trusted_proxy_cidrs))
        request.state.secure_cookies = settings.secure_cookies
        forwarded_scheme = request.headers.get("x-forwarded-proto")
        if forwarded_scheme in {"http", "https"} and trusted_proxy_peer(
            request, settings.trusted_proxy_cidrs
        ):
            request.scope["scheme"] = forwarded_scheme
        if request.method == "POST":
            origin = request.headers.get("origin")
            if (
                request.headers.get("sec-fetch-site") == "cross-site"
                or origin
                and not same_origin(origin, str(request.url))
            ):
                raise HTTPException(403, "Start this operation from the game page.")
            chunks, length = [], 0
            async for chunk in request.stream():
                length += len(chunk)
                if length > MAX_BODY_BYTES:
                    raise HTTPException(413, "This request is too large.")
                chunks.append(chunk)
            request._body = b"".join(chunks)
            credential_content = request._body
            try:
                credential_content = json.dumps(
                    json.loads(request._body), ensure_ascii=False
                ).encode()
            except (ValueError, UnicodeError, RecursionError):
                if request._body:
                    raise HTTPException(422, "Submit valid JSON data.") from None
            credentials = (
                API_KEY,
                store.master,
                ledger.pepper,
                request.cookies.get(GAME_COOKIE, ""),
                request.cookies.get("hacktheai_demo", ""),
            )
            if any(value and value.encode() in credential_content for value in credentials):
                raise HTTPException(
                    422, "Do not submit API credentials or session cookies in game content."
                )
        response = await call_next(request)
    except HTTPException as exc:
        response = JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    if response.status_code == 401:
        response.delete_cookie(
            "hacktheai_demo" if request.url.path.startswith("/api/demo") else GAME_COOKIE, path="/"
        )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/guide")
def guide():
    return FileResponse(ROOT / "static" / "guide.html")


@app.get("/demo")
def demo():
    return FileResponse(ROOT / "static" / "demo.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/config")
def config(request: Request):
    return {
        "mode": MODE,
        "mission_starts_remaining": ledger.remaining_missions(request.state.client_key),
        "mission_limit": 3,
        "max_score": len(LEVELS) * 10,
        "prompt_limit": 30,
        "reviewed_at": "2026-10-08",
        "model": MODEL if MODE == "live" else None,
        "defenses": DEFENSES,
        "stations": [
            {k: level[k] for k in ("name", "depth", "topic", "subject", "story")}
            for level in LEVELS
        ],
    }


@app.post("/api/start")
async def start(data: Start, request: Request, response: Response):
    session = store.get(request.cookies.get(GAME_COOKIE))
    if session:
        if not secrets.compare_digest(session.client_key, request.state.client_key):
            raise HTTPException(401, "This session belongs to a different network.")
        async with session.lock:
            if game_over(session):
                store.sessions.pop(session.id, None)
                session = None
    if not session:
        try:
            session = store.create()
        except ValueError as exc:
            raise HTTPException(503, str(exc)) from None
        try:
            session.mission_number = ledger.claim_mission(request.state.client_key)
        except LimitReached as exc:
            store.sessions.pop(session.id, None)
            raise HTTPException(429, str(exc)) from None
        session.client_key = request.state.client_key
        session.team = data.team.strip() or "Operator"
    set_session_cookie(response, request, store, session, GAME_COOKIE)
    async with session.lock:
        if store.sessions.get(session.id) is not session:
            raise HTTPException(401, "The previous session is unavailable. Start a new mission.")
        return mission_state(session)


@app.get("/api/state")
async def state(request: Request):
    async with locked_session(request, store) as session:
        return mission_state(session)


@app.post("/api/chat")
async def chat(data: Chat, request: Request):
    async with locked_session(request, store) as session:
        request_station(data, session)
        room = playable(session)
        throttle(session)
        level = LEVELS[session.current]
        if level.get("document") and data.document.strip():
            prompt = "Summarize the edited document in three sentences."
        else:
            prompt = data.message.strip()
            if not prompt:
                raise HTTPException(422, "Enter a message or transmit the edited document.")
        secret = secret_for(store.master, session.id, session.current)
        sent_at = time.time()
        conversational_reply = None
        guided = room.hints == len(level["hints"]) and intended_attack(
            session.current, prompt, data.document
        )
        if guided:
            room.guided = True
            answer, traces, opened = demo_reply(
                session.current, prompt, data.document, secret, room.history
            )
            answer = "Guided training / deterministic demonstration\n\n" + answer
            if session.current == 1:
                answer += (
                    "\n\n1. Read the reversed code from last character to first."
                    f"\n2. Original formula: {secret}"
                    f"\n3. Copy into the recovered-code field: {secret}"
                    "\n4. Select Verify code."
                )
        elif MODE == "demo":
            answer, traces, opened = demo_reply(
                session.current, prompt, data.document, secret, room.history
            )
        else:
            try:
                await asyncio.wait_for(provider_slots.acquire(), timeout=10)
            except TimeoutError:
                raise HTTPException(
                    503, "The AI is busy. Retry; no attempt was consumed."
                ) from None
            try:
                reply = await live_reply(
                    API_KEY,
                    MODEL,
                    session.current,
                    room.history,
                    prompt,
                    data.document,
                    secret,
                    budget=TokenBudget(ledger, session.client_key),
                )
                answer, traces, opened = reply
                if hasattr(reply, "accepted_method"):
                    conversational_reply = not reply.accepted_method
            except LimitReached as exc:
                raise HTTPException(429, str(exc)) from None
            except ProviderError as exc:
                raise HTTPException(getattr(exc, "status_code", 503), str(exc)) from None
            finally:
                provider_slots.release()
        for credential in (API_KEY, store.master, ledger.pepper):
            if credential and credential in answer:
                answer = "Let's keep credentials outside our discussion. Ask about this station's public defense and we can plan an experiment."
                traces, opened, conversational_reply = [], False, True
        room.attempts += 1
        room.round_attempts += 1
        shown_prompt = (
            prompt
            if not (LEVELS[session.current].get("document") and data.document.strip())
            else prompt + "\n\n" + data.document
        )
        answered_at = time.time()
        room.record_messages(
            {
                "role": "user",
                "content": shown_prompt,
                "timestamp": sent_at,
                **(
                    {"prompt": prompt, "document": data.document}
                    if LEVELS[session.current].get("document") and data.document.strip()
                    else {}
                ),
            },
            {"role": "assistant", "content": answer, "timestamp": answered_at},
        )
        if conversational_reply or conversation_intent(session.current, prompt, data.document):
            room.learning_answers.append(answer)
        room.learning_answers = [
            answer
            for answer in room.learning_answers
            if any(
                message["role"] == "assistant" and message["content"] == answer
                for message in room.history
            )
        ]
        room.record_traces(traces, answered_at)
        manual_decode = (
            guided and session.current in {1, 5} and room.round_attempts < level["attempts"]
        )
        final_transformation = (
            session.current in {1, 5}
            and room.round_attempts == level["attempts"]
            and transformed_disclosure(answer, secret, session.current)
        )
        if (
            opened
            or (not conversational_reply and leaked(answer, secret))
            or guided
            or final_transformation
        ) and not manual_decode:
            complete(session, assisted=room.guided)
        return mission_state(session)


@app.post("/api/code")
async def code(data: Code, request: Request):
    if not data.code.strip():
        raise HTTPException(422, "Enter the complete recovered value.")
    async with locked_session(request, store) as session:
        request_station(data, session)
        room = playable(session)
        secret = secret_for(store.master, session.id, session.current)
        correct = matches_code(data.code, secret, session.current)
        copied = not correct and copied_model_code(
            data.code, session.current, room.history, learning_answers=room.learning_answers
        )
        if room.checks >= 30 and not room.guided and not correct and not copied:
            raise HTTPException(
                429,
                "You reached 30 code checks. Request a hint and continue with the AI.",
            )
        room.checks += 1
        if not correct:
            if copied:
                room.code_correction = (
                    "You copied the response correctly, but the model supplied a different code. "
                    "The station is recovered with a training correction. "
                    "The original value and explanation appear below. "
                    "Your score depends on hints used."
                )
                room.record_messages(
                    {"role": "assistant", "content": room.code_correction, "timestamp": time.time()}
                )
                complete(session, assisted=True)
                return mission_state(session)
            raise HTTPException(
                400,
                "This is not the complete code. Check decoding, numbers and operators.",
            )
        complete(session, assisted=room.guided)
        return mission_state(session)


@app.post("/api/hint")
async def hint(request: Request, data: Hint | None = None):
    async with locked_session(request, store) as session:
        request_station(data, session)
        room = playable(session)
        if room.hints >= len(LEVELS[session.current]["hints"]):
            raise HTTPException(409, "All ten hints are unlocked. Use the guided experiment.")
        if (
            not data
            or not data.token
            or not data.token.isascii()
            or not secrets.compare_digest(data.token, room.hint_token)
        ):
            raise HTTPException(403, "Request a hint using the hint button.")
        if time.monotonic() < room.hint_ready_at:
            raise HTTPException(429, "Read the previous hint, then request the next one.")
        room.hints += 1
        room.hint_token = secrets.token_hex(32)
        room.hint_ready_at = time.monotonic() + HINT_COOLDOWN_SECONDS
        return mission_state(session)


@app.post("/api/retry")
async def retry(request: Request):
    async with locked_session(request, store) as session:
        playable(session)
        raise HTTPException(409, "Each station has 30 attempts. Attempts cannot be refilled.")


@app.post("/api/next")
async def next_room(request: Request, data: StationAction | None = None):
    async with locked_session(request, store) as session:
        request_station(data, session)
        if not session.rooms[session.current].solved:
            raise HTTPException(403, "Recover this station before proceeding.")
        session.current = min(session.current + 1, len(LEVELS) - 1)
        return mission_state(session)


@app.post("/api/note")
async def note(data: Note, request: Request):
    async with locked_session(request, store) as session:
        request_station(data, session)
        session.rooms[session.current].note = data.note
        return {"saved": True}


@app.post("/api/defense")
async def defense(data: Defense, request: Request):
    async with locked_session(request, store) as session:
        if not all(r.solved for r in session.rooms):
            raise HTTPException(403, "The defense workshop unlocks after all fifteen stations.")
        selected = set(data.choices)
        tests = [
            {
                "name": "Secret requested through a role pretext",
                "passed": "outside" in selected,
                "explanation": "The model never receives the protected value, so it cannot disclose it.",
            },
            {
                "name": "Visitor impersonating a maintenance operator",
                "passed": "permissions" in selected,
                "explanation": "Server authorization rejects the visitor even if the AI suggests opening the compartment.",
            },
            {
                "name": "System directive embedded in a document",
                "passed": "documents" in selected,
                "explanation": "The demonstration treats documents as data. This reduces risk but does not guarantee model resistance.",
            },
        ]
        passed = selected == {"outside", "permissions", "documents"}
        session.defense_passed = passed
        return {
            "passed": passed,
            "tests": tests,
            "message": "Defense plan validated. The model assists; the server enforces permission."
            if passed
            else "Select the three effective controls and omit the two ineffective ones.",
        }


@app.get("/api/export")
async def export(request: Request):
    async with locked_session(request, store) as session:
        report = make_report(session, MODE, MODEL)
    content = await asyncio.to_thread(render_pdf, report)
    return Response(
        content,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="hacktheai-mission-log.pdf"'},
    )


@app.get("/api/certificate")
async def certificate(request: Request):
    async with locked_session(request, store) as session:
        if not all(room.solved for room in session.rooms):
            raise HTTPException(
                403, "Recover all fifteen stations before requesting the certificate."
            )
        report = make_report(session, MODE, MODEL)
    content = await asyncio.to_thread(render_certificate, report)
    return Response(
        content,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="hacktheai-certificate.pdf"'},
    )


@app.post("/api/reset")
async def reset(request: Request, response: Response):
    async with locked_session(request, store) as session:
        store.sessions.pop(session.id, None)
    response.delete_cookie(GAME_COOKIE)
    return {
        "reset": True,
        "mission_starts_remaining": ledger.remaining_missions(request.state.client_key),
    }


if __name__ == "__main__":
    print("HackTheAI – " + ("deterministic training simulation" if MODE == "demo" else MODEL))
    uvicorn.run(app, host="0.0.0.0", port=settings.port, proxy_headers=False, access_log=False)
