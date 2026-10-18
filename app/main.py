from datetime import datetime, timezone
from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.db.session import get_db
from app.api.auth import router as auth_router
from app.api.suppliers import router as suppliers_router
from app.api.buyers import router as buyers_router
from app.api.currency import router as currency_router
from app.api.dashboard import router as dashboard_router
from app.api.invoices import router as invoices_router
from app.core.security import verify_password, get_password_hash

app = FastAPI(
    title="AI-Driven Dynamic Discounting & Supply Chain Liquidity Engine API",
    description="Liquidity Engine API with Authentication, Suppliers, Buyers & Role-Based Access Control",
    version="0.3.0",
)

# 1. CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 2. Global Exception Handlers

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Global handler for validation errors (422) with consistent {detail, code} body."""
    errors = []
    for err in exc.errors():
        loc = " -> ".join(str(l) for l in err.get("loc", []))
        msg = err.get("msg", "")
        errors.append(f"{loc}: {msg}" if loc else msg)
    detail_str = "; ".join(errors) if errors else "Validation error"
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": detail_str, "code": "VALIDATION_ERROR"},
    )


@app.exception_handler(IntegrityError)
async def integrity_exception_handler(request: Request, exc: IntegrityError):
    """Global handler for database integrity errors (409) with readable message."""
    orig = str(exc.orig) if hasattr(exc, "orig") and exc.orig else str(exc)
    orig_lower = orig.lower()
    if "unique" in orig_lower or "duplicate" in orig_lower or "already exists" in orig_lower:
        detail = "Resource conflict: a record with the specified unique key already exists."
    elif "foreign key" in orig_lower or "violates foreign key" in orig_lower:
        detail = "Resource conflict: foreign key reference violation."
    elif "check constraint" in orig_lower:
        detail = f"Resource constraint violation: {orig}"
    else:
        detail = f"Database integrity error: {orig}"

    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": detail, "code": "INTEGRITY_ERROR"},
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Global handler for HTTP exceptions ensuring consistent {detail, code} body."""
    if exc.status_code == status.HTTP_404_NOT_FOUND:
        code = "NOT_FOUND"
    elif exc.status_code == status.HTTP_409_CONFLICT:
        code = "INTEGRITY_ERROR"
    elif exc.status_code == status.HTTP_401_UNAUTHORIZED:
        code = "UNAUTHORIZED"
    elif exc.status_code == status.HTTP_403_FORBIDDEN:
        code = "FORBIDDEN"
    elif exc.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY:
        code = "VALIDATION_ERROR"
    elif exc.status_code == status.HTTP_400_BAD_REQUEST:
        code = "BAD_REQUEST"
    else:
        code = f"HTTP_{exc.status_code}"

    detail = exc.detail
    headers = exc.headers

    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": detail, "code": code},
        headers=headers,
    )


# 3. Include Routers
app.include_router(auth_router)
app.include_router(suppliers_router)
app.include_router(buyers_router)
app.include_router(invoices_router)
app.include_router(currency_router)
app.include_router(dashboard_router)


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
