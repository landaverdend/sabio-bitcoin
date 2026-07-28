import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from backend.auth import router as auth_router
from backend.chat import close_session_storage
from backend.chat import router as chat_router
from backend.comms import router as comms_router
from backend.irc import router as irc_router
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
app.include_router(comms_router)
app.include_router(irc_router)
app.include_router(people_router)


@app.get("/ping")
def ping() -> dict:
    return {"message": "pong"}


# Local dev never hits this: frontend/dist only exists after `npm run build`,
# which the Docker image runs but a bare `uvicorn --reload` checkout doesn't
# -- the frontend is served by its own Vite dev server (proxying API calls
# back here) instead. In the deployed container this is the only server
# process, so it also has to hand back the built SPA.
_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if _FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=_FRONTEND_DIST / "assets"), name="assets")

    # Registered last so every API route above still wins -- this only ever
    # catches paths meant for React Router (/chat, /code/core, /people/123,
    # ...). Serves a real static file if the path happens to hit one
    # (favicon.svg) and falls back to index.html otherwise, letting the SPA's
    # own router take over client-side.
    @app.get("/{full_path:path}")
    async def spa(full_path: str) -> FileResponse:
        candidate = _FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_FRONTEND_DIST / "index.html")
