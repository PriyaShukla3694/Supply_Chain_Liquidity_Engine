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

4. **Database Migrations (Alembic):**
   - Apply migrations to head:
     ```bash
     docker compose exec backend alembic upgrade head
     ```
   - Generate a new revision:
     ```bash
     docker compose exec backend alembic revision --autogenerate -m "migration_description"
     ```
   - Rollback migration:
     ```bash
     docker compose exec backend alembic downgrade -1
     ```
   - View current migration status:
     ```bash
     docker compose exec backend alembic current
     ```

## Real vs. Placeholder Features

- **Real Database Session Setup**: SQLAlchemy 2.0 is configured to connect to PostgreSQL (pgvector). The `/health/db` endpoint tests this connection live.
- **Complete Database Schema & Migrations**: All business entities (users, companies, buyers, suppliers, invoices, payments, transactions, cash_flows, risk_scores, discount_offers, forecasts, model_predictions, documents, document_chunks, audit_logs, business_rules) are implemented in `app/models/` and managed with Alembic.
- **In-Memory JWT Auth**: The registration and login endpoints are functional skeleton routes.
