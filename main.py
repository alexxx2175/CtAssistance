
# main.py — FastAPI backend (Railway/any hosting)
# Endpoints:
#   GET  /start -> {"thread_id": "..."}
#   POST /chat  -> body: {"thread_id": "...", "message": "..."}
# Uses OpenAI Assistants API via REST.

import os
from typing import Dict
import time
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
ASSISTANT_ID = os.environ.get("ASSISTANT_ID")

app = FastAPI(title="CT Marketing Chat Backend")

# CORS (restrict to your domain in production)
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if ALLOWED_ORIGINS != ["*"] else ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatIn(BaseModel):
    thread_id: str
    message: str

class ChatOut(BaseModel):
    reply: str
    thread_id: str

OPENAI_BASE = "https://api.openai.com/v1"

def _headers() -> Dict[str, str]:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return {}
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

@app.get("/start")
def start() -> Dict[str, str]:
    if not OPENAI_API_KEY or not ASSISTANT_ID:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY or ASSISTANT_ID not configured")
    with httpx.Client(timeout=30.0) as client:
        r = client.post(f"{OPENAI_BASE}/threads", headers=_headers(), json={})
        if r.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"OpenAI error: {r.text}")
        data = r.json()
        return {"thread_id": data["id"]}

@app.post("/chat", response_model=ChatOut)
def chat(inp: ChatIn) -> ChatOut:
    if not OPENAI_API_KEY or not ASSISTANT_ID:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY or ASSISTANT_ID not configured")

    thread_id = inp.thread_id
    user_message = inp.message

    with httpx.Client(timeout=60.0) as client:
        # 1) Add user message
        r = client.post(
            f"{OPENAI_BASE}/threads/{thread_id}/messages",
            headers=_headers(),
            json={"role": "user", "content": user_message},
        )
        if r.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"OpenAI error (add message): {r.text}")

        # 2) Start run
        r = client.post(
            f"{OPENAI_BASE}/threads/{thread_id}/runs",
            headers=_headers(),
            json={"assistant_id": ASSISTANT_ID},
        )
        if r.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"OpenAI error (start run): {r.text}")
        run = r.json()
        run_id = run["id"]

        # 3) Poll run status
        status = run.get("status")
        checks = 0
        while status in ("queued", "in_progress"):
            time.sleep(0.9)
            r = client.get(
                f"{OPENAI_BASE}/threads/{thread_id}/runs/{run_id}",
                headers=_headers(),
            )
            if r.status_code >= 400:
                raise HTTPException(status_code=502, detail=f"OpenAI error (check run): {r.text}")
            status = r.json().get("status")
            checks += 1
            if checks > 60:
                break

        if status != "completed":
            return ChatOut(reply="Mi sto prendendo qualche secondo in più per elaborare, riprova tra poco.", thread_id=thread_id)

        # 4) Read last assistant message
        r = client.get(
            f"{OPENAI_BASE}/threads/{thread_id}/messages?limit=10",
            headers=_headers(),
        )
        if r.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"OpenAI error (read messages): {r.text}")
        msgs = r.json().get("data", [])
        assistant_msgs = [m for m in msgs if m.get("role") == "assistant"]
        assistant_msgs.sort(key=lambda m: m.get("created_at", 0))
        last = assistant_msgs[-1] if assistant_msgs else None

        reply_text = "Nessuna risposta."
        if last and last.get("content"):
            for block in last["content"]:
                if block.get("type") == "text" and block.get("text", {}).get("value"):
                    reply_text = block["text"]["value"]
                    break

        return ChatOut(reply=reply_text, thread_id=thread_id)
