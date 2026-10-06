# AI-Driven Dynamic Discounting & Supply Chain Liquidity Engine

This is the repository scaffold for Week 1 of the project.

## Directory Structure

```text
├── app/
│   ├── core/
│   │   └── config.py        # Settings loader using Pydantic Settings
│   ├── db/
│   │   └── session.py       # SQLAlchemy session and engine initialization
│   ├── ml/
│   │   └── .gitkeep         # Placeholder for Week 3 Payment Delay prediction
│   ├── models/
│   │   └── .gitkeep         # Placeholder for Week 1/2 SQLAlchemy models
│   └── main.py              # FastAPI app containing health endpoints & Auth skeleton
├── .env.example             # Template for configuration variables
├── .gitignore               # Excludes python artifacts, local environments & pgdata
├── CONTRIBUTING.md          # Branching & PR workflow guidelines
├── db/
│   └── init.sql             # Postgres init script (CREATE EXTENSION vector)
├── docker-compose.yml       # Spins up Postgres (with pgvector) + FastAPI backend
├── Dockerfile               # Builds backend container
├── requirements.txt         # Project dependencies
└── business_rules.md        # Documented business rules (source of truth)
```

## Setup & Running Locally

1. **Copy Environment Template:**
   ```bash
   cp .env.example .env
   ```

2. **Run with Docker Compose:**
   ```bash
   docker compose up --build -d
   ```
   This spins up:
   - **Postgres (pgvector)**: Exposed on port `5432` with database `liquidity_engine`.
   - **FastAPI backend**: Exposed on port `8000` with hot-reloading.

3. **Verify API Endpoints:**
   - **Health Check**: `GET http://localhost:8000/health`
   - **DB Connectivity Health Check**: `GET http://localhost:8000/health/db`
   - **Interactive Swagger Docs**: `GET http://localhost:8000/docs`

## Real vs. Placeholder Features

- **Real Database Session Setup**: SQLAlchemy is configured to connect to PostgreSQL. The `/health/db` endpoint tests this connection live.
- **In-Memory JWT Auth**: The registration and login endpoints are functional skeleton routes.
- **Next Step - Real DB Models**: Wiring the auth and business entities to PostgreSQL tables in `app/models/`.
