"""Isolated, unlimited training API."""

from collections.abc import Callable

from fastapi import APIRouter, HTTPException, Request, Response

from game import Store
from schemas import Chat, Code
from tutorial import tutorial_check, tutorial_exercise, tutorial_reply
from web_sessions import TUTORIAL_COOKIE, find_session, set_session_cookie


def create_tutorial_router(get_store: Callable[[], Store]) -> APIRouter:
    router = APIRouter(prefix="/api/demo")

    def exercise(request: Request) -> dict:
        store = get_store()
        session = find_session(
            request,
            store,
            TUTORIAL_COOKIE,
            "Training session expired. Refresh to continue.",
        )
        return tutorial_exercise(store.master, session.id)

    @router.post("/start")
    async def start(request: Request, response: Response):
        store = get_store()
        session = store.get(request.cookies.get(TUTORIAL_COOKIE))
        if session is None:
            try:
                session = store.create()
            except ValueError as exc:
                raise HTTPException(503, str(exc)) from None
        set_session_cookie(response, request, store, session, TUTORIAL_COOKIE)
        return {"ready": True}

    @router.post("/chat")
    async def chat(data: Chat, request: Request):
        if not data.message.strip():
            raise HTTPException(422, "Enter a request for the training guard.")
        return tutorial_reply(exercise(request), data.message)

    @router.post("/document")
    async def document(data: Chat, request: Request):
        if not data.document.strip():
            raise HTTPException(422, "The practice report must not be empty.")
        return tutorial_reply(exercise(request), data.document, document=True)

    @router.post("/code")
    async def code(data: Code, request: Request):
        current = exercise(request)
        solved = tutorial_check(current, data.code)
        return {"solved": solved, **({"discovery": current} if solved else {})}

    @router.post("/reveal")
    async def reveal(request: Request):
        return {"discovery": exercise(request)}

    return router
