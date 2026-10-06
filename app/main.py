from datetime import datetime, timezone
from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.sql import text

from app.db.session import get_db
from app.api.auth import router as auth_router
from app.core.security import verify_password, get_password_hash

app = FastAPI(
    title="AI-Driven Dynamic Discounting & Supply Chain Liquidity Engine API",
    description="Liquidity Engine API with Authentication & Role-Based Access Control",
    version="0.2.0",
)

# Include Authentication and RBAC endpoints
app.include_router(auth_router)


# --- Health Endpoints ---

@app.get("/health", status_code=status.HTTP_200_OK, tags=["Health"])
def read_health():
    """
    Service health check. Checks if API is running.
    """
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/health/db", status_code=status.HTTP_200_OK, tags=["Health"])
def read_db_health(db=Depends(get_db)):
    """
    Database connectivity check. Queries DB with simple SELECT 1 statement.
    """
    try:
        db.execute(text("SELECT 1"))
        return {
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database connection failed: {str(e)}",
        )
