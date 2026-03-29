# Backend — Local Development

This folder contains the FastAPI orchestrator and service adapters. For local development we provide a `docker-compose.yml` at the repo root which brings up Postgres, Redis, MinIO, the backend, and the frontend.

Quick start (from repo root):

```bash
# Start services (builds backend dependencies inside container)
docker compose up
```

Environment
- Copy `backend/.env.sample` → `backend/.env` if you want to run the backend outside compose.
- The compose file injects sensible defaults for `DATABASE_URL`, `MINIO_*`, and `REDIS_URL`.

Notes
- `TA-Lib` requires native libraries; the simple `python:3.11-slim` image used in compose may need build tools to install `ta-lib`. If installation fails inside the container, install system dependencies or prebuild a custom image.
- External LLM / Gemini keys are optional for local dev. Leave `GEMINI_API_KEY` empty to use mock fallbacks.

Useful endpoints
- API docs: http://localhost:8000/docs
- Signals endpoint example: http://localhost:8000/api/signals?symbol=RELIANCE.NS

If you want I can also:
- Add a small Makefile to simplify common commands
- Create a Dockerfile that pre-installs binary deps (ta-lib) to make `docker compose up` more reliable
