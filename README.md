# AI Data Lab (FastAPI backend)

FastAPI + SQLite (SQLModel) metadata service for an "AI data lab" app. Stores users/projects/datasets/prompts and is designed to stream uploaded/scraped artifacts to S3-compatible storage.

## Requirements

- Python 3.11+

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configure environment

SQLite is local by default (`sqlite:///./db.sqlite3`).

S3 settings are read from environment variables:

- `S3_BUCKET` (required for S3 uploads)
- `S3_REGION` (optional)
- `S3_ENDPOINT_URL` (optional; useful for MinIO/localstack)
- Standard AWS variables used by `boto3` like `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`

Optional:

- `OLLAMA_BASE_URL` (default `http://localhost:11434`)
- `OLLAMA_MODEL` (default `llama3.2:latest`)

You can put these in a `.env` file in the repo root.

If `S3_BUCKET` is not set, the app now falls back to local file storage under `.local_storage/` for development.

## Run

```bash
uvicorn app.main:app --reload --port 8000
```

Backend will be at `http://localhost:8000` and CORS is enabled for `http://localhost:5173`.

### Run frontend + backend in one terminal

From the repo root:

```bash
make dev
```

This starts:

- FastAPI backend at `http://localhost:8000`
- React frontend at `http://localhost:5173`

Press `Ctrl+C` once to stop both.

## Frontend (React + TypeScript SPA)

```bash
cd frontend
npm install
npm run dev
```

Optional env var in `frontend/.env`:

- `VITE_API_BASE_URL=http://localhost:8000/api`

## API

- `GET /health`
- `CRUD /api/projects`
- `GET /api/projects/{project_id}/summary`
- `GET|POST /api/projects/{project_id}/datasets`
- `GET|POST /api/projects/{project_id}/prompts` (optional query param: `tab_name`)

