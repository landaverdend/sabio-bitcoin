from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.repo import router as repo_router

app = FastAPI(title="Sabio Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(repo_router)


@app.get("/ping")
def ping() -> dict:
    return {"message": "pong"}
