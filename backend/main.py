import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from backend.auth import router as auth_router
from backend.chat import close_session_storage
from backend.chat import router as chat_router
from backend.people import router as people_router
from backend.repo import router as repo_router

@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    close_session_storage()


app = FastAPI(title="Sabio Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
    # Needed for the login (Nostr auth) session cookie to actually reach the
    # backend on cross-origin requests -- irrelevant when the frontend talks
    # to this API through Vite's dev proxy (same-origin from the browser's
    # view), but correct regardless of how it's ever deployed.
    allow_credentials=True,
)
# Backs request.session (see backend/auth.py) -- a signed, not encrypted,
# cookie holding just the logged-in pubkey. SESSION_SECRET must come from
# the environment: a secret generated fresh at every restart would silently
# log everyone out on every backend reload.
app.add_middleware(SessionMiddleware, secret_key=os.environ["SESSION_SECRET"])

app.include_router(auth_router)
app.include_router(repo_router)
app.include_router(chat_router)
app.include_router(people_router)


@app.get("/ping")
def ping() -> dict:
    return {"message": "pong"}
