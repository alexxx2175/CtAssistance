
# CT Marketing — Backend (FastAPI + Railway)

Espone:
- `GET  /start` → crea un thread e restituisce `thread_id`
- `POST /chat`  → `{ "thread_id": "...", "message": "..." }` → `{ "reply": "...", "thread_id": "..." }`

## Avvio locale
```bash
pip install -r requirements.txt
export OPENAI_API_KEY=sk-...
export ASSISTANT_ID=asst_...
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Test:
```bash
curl http://localhost:8000/start
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" -d '{"thread_id":"<ID>","message":"Ciao!"}'
```

## Deploy su Railway
1. Crea un repo GitHub con questi file.
2. Railway → New Project → Deploy from GitHub → seleziona il repo.
3. In **Variables**, aggiungi:
   - `OPENAI_API_KEY` (segreto)
   - `ASSISTANT_ID`
   - (opzionale) `ALLOWED_ORIGINS=https://www.ctmarketing.it`
4. In **Settings → Start Command** metti:
```
uvicorn main:app --host 0.0.0.0 --port $PORT
```
5. Deploy → copia l'URL `https://<app>.railway.app`

Endpoint per WordPress:
- Start: `https://<app>.railway.app/start`
- Chat:  `https://<app>.railway.app/chat`
