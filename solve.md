## SOLVED

**Backend n8n routes created** — Added `backend/app/api/routes/n8n.py` with three dedicated endpoints (`/api/v1/n8n/metrics/summary`, `/api/v1/n8n/clients/at-risk`, `/api/v1/n8n/agent/reports`). These replace the missing routes the workflows were calling into void. Workflow URLs were kept as-is since `/api/v1/n8n/...` was always the right prefix — what was missing was the backend side.

**Auth fixed** — Routes are protected by `X-API-Key` header validation against `settings.N8N_API_KEY`. The workflows already send this header correctly. No JWT needed for n8n.

**`/agent/reports` route created** — No stored reports table exists. The new endpoint generates a live digest from `service.get_summary()` and returns it in the shape the workflow expects (`summary`, `recommendations`, `kpis_json`).

**`N8N_API_KEY` added to `backend/.env`** — Set to `test-local-n8n-key`, matching the value already in `n8n/stack.env`. Both sides now agree.

**Router registered** — `n8n_router` imported and mounted in `backend/app/main.py`.

---

Start/enable Docker Desktop on Windows.

Fix n8n workflow API URLs:

Replace /api/v1/n8n/metrics/summary with /api/v1/bad-debts/metrics/summary.
Replace /api/v1/n8n/clients/at-risk with /api/v1/bad-debts/clients/at-risk.
Replace invalid /api/v1/bad-debts/agent/reports usage or create that backend route.
Add a backend API access method for n8n:

Either create public/internal n8n-only routes protected by N8N_API_KEY.
Or make n8n authenticate and send a valid JWT/session token.
Update the n8n workflows to send the required auth header, for example:

X-N8N-API-Key: <key>
or Authorization: Bearer <token>.
Add/confirm backend .env values:

N8N_API_KEY=...
BACKEND_PUBLIC_BASE_URL=http://127.0.0.1:8000
Add/confirm n8n/stack.env values:

PFE_API_URL=http://host.docker.internal:8000
PFE_DASHBOARD_URL=http://localhost:5173/dashboard/bad-debts
PFE_REPORT_EMAIL=...
Configure SMTP credentials inside n8n, not in Git.

Import the corrected workflow JSON into n8n.

Test each HTTP Request node manually in n8n.

Test the full workflow manually.

Enable the Cron/Schedule trigger in n8n for automatic execution.

Make n8n start automatically:

Keep restart: unless-stopped in n8n/docker-compose.yml.
Ensure Docker Desktop starts with Windows.
Start n8n together with backend using a startup script:

Start backend FastAPI.
Run docker compose up -d inside the n8n folder.
Optionally start frontend.
Add health checks:

Backend /api/v1/bad-debts/health.
n8n http://localhost:5678.
Verify final automation:

Backend running.
n8n running.
Workflow active.
Email sent successfully.
No failed executions in n8n logs.