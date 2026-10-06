from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user, get_current_user_optional, require_roles
from app.core.security import verify_password, get_password_hash, create_access_token
from app.models.user import User
from app.models.company import Company

router = APIRouter(tags=["Authentication & RBAC"])


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)
    email: Optional[str] = Field(None, max_length=255)
    role: Optional[str] = Field("analyst")
    company_id: Optional[int] = None


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    username: str
    email: Optional[str] = None
    role: str
    company_id: Optional[int] = None


class Token(BaseModel):
    access_token: str
    token_type: str


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=UserResponse)
def register(
    user_in: UserCreate,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Registers a user:
    - If 0 users exist: first user becomes role 'admin' and attaches to/creates default Company.
    - If users exist: only authenticated admins can create new users and choose roles.
    """
    total_users = db.query(User).count()

    if total_users == 0:
        assigned_role = "admin"
        # Ensure default company row exists
        company = db.query(Company).first()
        if not company:
            company = Company(name="Default Company", industry="Supply Chain")
            db.add(company)
            db.commit()
            db.refresh(company)
        company_id = company.id
    else:
        # After the first user, registration requires an authenticated admin
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required to register users",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only administrators can create users",
            )

        assigned_role = user_in.role or "analyst"
        if assigned_role not in {"admin", "finance_manager", "analyst"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid role. Must be one of: admin, finance_manager, analyst",
            )

        company_id = user_in.company_id or current_user.company_id

    # Check uniqueness
    if db.query(User).filter(User.username == user_in.username).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )
    if user_in.email and db.query(User).filter(User.email == user_in.email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    new_user = User(
        username=user_in.username,
        email=user_in.email,
        hashed_password=get_password_hash(user_in.password),
        role=assigned_role,
        company_id=company_id,
        is_active=True,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@router.post("/login", response_model=Token)
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    Authenticates a user using OAuth2 username & password form.
    Returns a JWT containing subject, role, and company_id.
    """
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user account",
        )

    access_token = create_access_token(
        data={
            "sub": user.username,
            "role": user.role,
            "company_id": user.company_id,
        }
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/users/me", response_model=UserResponse)
def read_users_me(current_user: User = Depends(get_current_user)):
    """
    Returns current authenticated user details without password hash.
    """
    return current_user


@router.get("/admin/ping")
def admin_ping(current_user: User = Depends(require_roles("admin"))):
    """
    Admin-only route demonstrating RBAC.
    """
    return {
        "message": "admin pong",
        "user": current_user.username,
        "role": current_user.role,
    }


@router.get("/finance/ping")
def finance_ping(current_user: User = Depends(require_roles("admin", "finance_manager"))):
    """
    Finance Manager or Admin route demonstrating RBAC.
    """
    return {
        "message": "finance pong",
        "user": current_user.username,
        "role": current_user.role,
    }
