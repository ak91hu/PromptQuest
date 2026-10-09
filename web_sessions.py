"""Signed session cookies and mutation locks."""

import os
import secrets
import time
from contextlib import asynccontextmanager

from fastapi import HTTPException, Request, Response

from game import Session, Store
from settings import SESSION_TTL_SECONDS

GAME_COOKIE = "hacktheai_session"
TUTORIAL_COOKIE = "hacktheai_demo"


def set_session_cookie(
    response: Response, request: Request, store: Store, session: Session, name: str
) -> None:
    if not session.client_key:
        session.client_key = request.state.client_key
    elif not secrets.compare_digest(session.client_key, request.state.client_key):
        raise HTTPException(401, "This session belongs to a different network.")
    response.set_cookie(
        name,
        store.token(session),
        httponly=True,
        samesite="strict",
        secure=bool(os.getenv("RENDER") or os.getenv("NF_HOSTS"))
        or request.url.scheme == "https"
        or request.state.secure_cookies,
        path="/",
        max_age=max(0, SESSION_TTL_SECONDS - int(time.time() - session.created)),
    )


def find_session(request: Request, store: Store, name: str, error: str) -> Session:
    session = store.get(request.cookies.get(name))
    if session is None or not secrets.compare_digest(session.client_key, request.state.client_key):
        raise HTTPException(401, error)
    return session


@asynccontextmanager
async def locked_session(request: Request, store: Store):
    error = "Your session expired or the server restarted. Start a new mission."
    session = find_session(request, store, GAME_COOKIE, error)
    async with session.lock:
        if store.get(request.cookies.get(GAME_COOKIE)) is not session:
            raise HTTPException(401, error)
        yield session
