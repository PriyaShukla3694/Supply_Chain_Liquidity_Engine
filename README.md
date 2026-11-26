# AI-Driven Dynamic Discounting & Supply Chain Liquidity Engine

FastAPI + React/TypeScript platform for supply chain invoice intelligence, buyer risk scoring, late-payment prediction (`payment_risk_v1`), dynamic discounting optimization, and RAG-powered policy Q&A.

## Tech Stack

- **Backend**: FastAPI, SQLAlchemy 2.0, Pydantic v2, Uvicorn
- **Database**: PostgreSQL 16 with `pgvector` extension, managed via Alembic migrations
- **Auth & RBAC**: OAuth2 password flow + JWT (`python-jose`) + `bcrypt` password hashing (`passlib`), with role guards (`admin`, `finance_manager`, `analyst`)
- **ML Pipeline**: Calibrated `payment_risk_v1` model (`models/payment_risk_v1.joblib`, 16 as-of features, XGBoost + isotonic/sigmoid calibration, lazy-loaded)
- **Frontend**: React 19, TypeScript, Vite, Tailwind CSS v4, React Router

## Directory Structure

```text
├── app/
│   ├── api/                 # FastAPI routers (auth, buyers, invoices, predict, discounts, rag, etc.)
│   ├── core/                # Config, security (JWT/bcrypt), currency, business rules
│   ├── db/                  # SQLAlchemy session and engine initialization
│   ├── ml/                  # ML feature definitions (16 as-of features)
│   ├── models/              # SQLAlchemy ORM models
│   ├── schemas/             # Pydantic request/response schemas
│   ├── services/            # Scoring, prediction, discount optimizer, RAG services
│   └── main.py              # FastAPI application entrypoint
├── alembic/                 # Alembic database migrations
├── db/
│   └── init.sql             # Postgres init script (CREATE EXTENSION vector)
├── docs/                    # Data dictionary, ML report & metrics
├── frontend/                # React + TypeScript + Vite web application
├── models/                  # Trained ML model artifacts (payment_risk_v1.joblib)
├── scripts/                 # Seed loader, buyer scoring, ML training & parity scripts
├── seed_data/               # Cleaned CSV datasets
├── tests/                   # Pytest backend test suite
├── docker-compose.yml       # Spins up Postgres (pgvector) + FastAPI backend
├── Dockerfile               # Builds backend container
├── requirements.txt         # Python dependencies
└── business_rules.md        # Locked business rules specification
```

## Setup & Running Locally

### 1. Copy Environment Template

```bash
cp .env.example .env
```

### 2. Run Backend & Database with Docker Compose

```bash
docker compose up --build -d
```

This spins up:
- **Postgres (`pgvector/pgvector:pg16`)**: Exposed on port `5432` with database `liquidity_engine`
- **FastAPI backend**: Exposed on port `8000` with hot-reloading (`DATABASE_URL=postgresql://<POSTGRES_USER>:<POSTGRES_PASSWORD>@db:5432/<POSTGRES_DB>`)

Verify API endpoints:
- **Health Check**: `GET http://localhost:8000/health`
- **DB Connectivity Health Check**: `GET http://localhost:8000/health/db`
- **Interactive Swagger Docs**: `GET http://localhost:8000/docs`

### 3. Database Migrations (Alembic)

- Apply migrations to head:
  ```bash
  docker compose exec backend alembic upgrade head
  ```
- Generate a new revision:
  ```bash
  docker compose exec backend alembic revision --autogenerate -m "migration_description"
  ```
- Rollback one migration:
  ```bash
  docker compose exec backend alembic downgrade -1
  ```
- View current migration status:
  ```bash
  docker compose exec backend alembic current
  ```

### 4. Load Seed Data

Idempotent loader that populates the default company, suppliers, buyers, invoices, cash flows, and discount offers:

```bash
docker compose exec backend python scripts/load_seed_data.py
```

### 5. Compute Buyer Risk Scores

Compute and persist buyer risk scores (`risk_scores` table) using `app/services/buyer_scoring.py`:

```bash
docker compose exec backend python scripts/compute_buyer_scores.py
```

Optional flags: `--as-of YYYY-MM-DD`, `--dry-run`.

### 6. Train the Payment Risk Model (`payment_risk_v1`)

Train, calibrate on validation, evaluate once on test, and export `models/payment_risk_v1.joblib`:

```bash
docker compose exec backend python scripts/train_payment_model.py
```

### 7. Run Backend Tests

Run the full pytest suite inside the backend container (with `DATABASE_URL` configured in `docker-compose.yml`):

```bash
docker compose exec backend pytest -q
```

### 8. Run the Frontend

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server runs at `http://localhost:5173/`. To create a production build and run TypeScript type-checking:

```bash
cd frontend
npm run build
```
