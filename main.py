# main.py — FastAPI backend (Railway)

import os, time
from typing import Dict
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
ASSISTANT_ID   = os.environ.get("ASSISTANT_ID")
OPENAI_BASE    = "https://api.openai.com/v1"

app = FastAPI(title="CT Marketing Chat Backend")

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

def _headers() -> Dict[str, str]:
    if not OPENAI_API_KEY:
        return {}
    return {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
        "OpenAI-Beta": "assistants=v2",   # <<< IMPORTANTE
    }

# Allinea le rotte a quelle che chiama Voiceflow
@app.get("/pv/start")
def start():
    if not OPENAI_API_KEY:
        raise HTTPException(500, "OPENAI_API_KEY not configured")
    with httpx.Client(timeout=30.0) as client:
        r = client.post(f"{OPENAI_BASE}/threads", headers=_headers(), json={})
        if r.status_code >= 400:
            raise HTTPException(502, f"OpenAI error: {r.text}")
        data = r.json()
        return {"thread_id": data["id"]}

@app.post("/pv/chat", response_model=ChatOut)
def chat(inp: ChatIn) -> ChatOut:
    if not OPENAI_API_KEY or not ASSISTANT_ID:
        raise HTTPException(500, "OPENAI_API_KEY or ASSISTANT_ID not configured")

    thread_id = inp.thread_id
    user_message = inp.message

    with httpx.Client(timeout=90.0) as client:
        # 1) Add user message
        r = client.post(
            f"{OPENAI_BASE}/threads/{thread_id}/messages",
            headers=_headers(),
            json={"role": "user", "content": user_message},
        )
        if r.status_code >= 400:
            raise HTTPException(502, f"OpenAI error (add message): {r.text}")

        # 2) Start run
        r = client.post(
            f"{OPENAI_BASE}/threads/{thread_id}/runs",
            headers=_headers(),
            json={"assistant_id": ASSISTANT_ID},
        )
        if r.status_code >= 400:
            raise HTTPException(502, f"OpenAI error (start run): {r.text}")
        run = r.json()
        run_id = run["id"]

        # 3) Poll
        status = run.get("status")
        for _ in range(60):
            if status not in ("queued", "in_progress"):
                break
            time.sleep(0.9)
            r = client.get(
                f"{OPENAI_BASE}/threads/{thread_id}/runs/{run_id}",
                headers=_headers(),
            )
            if r.status_code >= 400:
                raise HTTPException(502, f"OpenAI error (check run): {r.text}")
            status = r.json().get("status")

        if status != "completed":
            return ChatOut(
                reply="Mi sto prendendo qualche secondo in più per elaborare, riprova tra poco.",
                thread_id=thread_id,
            )

        # 4) Read last assistant message (ordina discendente e prendi il primo)
        r = client.get(
            f"{OPENAI_BASE}/threads/{thread_id}/messages?limit=10&order=desc",
            headers=_headers(),
        )
        if r.status_code >= 400:
            raise HTTPException(502, f"OpenAI error (read messages): {r.text}")
        msgs = r.json().get("data", [])
        reply_text = "Nessuna risposta."
        for m in msgs:
            if m.get("role") == "assistant":
                for block in m.get("content", []):
                    if block.get("type") == "text" and block.get("text", {}).get("value"):
                        reply_text = block["text"]["value"]
                        break
                break

        return ChatOut(reply=reply_text, thread_id=thread_id)
