from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user, require_roles
from app.models.supplier import Supplier
from app.models.user import User
from app.schemas.common import PaginatedResponse, PaginationParams
from app.schemas.supplier import SupplierCreate, SupplierRead, SupplierUpdate

router = APIRouter(prefix="/suppliers", tags=["Suppliers"])


@router.get(
    "",
    response_model=PaginatedResponse[SupplierRead],
    summary="List Suppliers",
    description="Lists all suppliers belonging to the authenticated user's company with pagination and filters.",
)
def list_suppliers(
    search: Optional[str] = Query(None, description="Search by supplier name or ID"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Supplier).filter(Supplier.company_id == current_user.company_id)

    if search:
        search_pattern = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Supplier.supplier_id.ilike(search_pattern),
                Supplier.name.ilike(search_pattern),
            )
        )

    if is_active is not None:
        query = query.filter(Supplier.is_active == is_active)

    total = query.count()
    items = (
        query.order_by(Supplier.supplier_id)
        .offset(pagination.offset)
        .limit(pagination.limit)
        .all()
    )

    return PaginatedResponse[SupplierRead](
        items=items,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get(
    "/{supplier_id}",
    response_model=SupplierRead,
    summary="Get Supplier Details",
    description="Retrieves a specific supplier by ID scoped to the authenticated user's company.",
)
def get_supplier(
    supplier_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    supplier = (
        db.query(Supplier)
        .filter(
            Supplier.supplier_id == supplier_id,
            Supplier.company_id == current_user.company_id,
        )
        .first()
    )
    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Supplier '{supplier_id}' not found",
        )
    return supplier


@router.post(
    "",
    response_model=SupplierRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create Supplier",
    description="Creates a new supplier attached to the current user's company. Requires 'admin' or 'finance_manager' role.",
)
def create_supplier(
    supplier_in: SupplierCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "finance_manager")),
):
    existing = db.query(Supplier).filter(Supplier.supplier_id == supplier_in.supplier_id).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Supplier with ID '{supplier_in.supplier_id}' already exists",
        )

    supplier_data = supplier_in.model_dump()
    supplier = Supplier(
        **supplier_data,
        company_id=current_user.company_id,
    )
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier


@router.patch(
    "/{supplier_id}",
    response_model=SupplierRead,
    summary="Update Supplier",
    description="Partially updates an existing supplier. Requires 'admin' or 'finance_manager' role.",
)
def update_supplier(
    supplier_id: str,
    supplier_in: SupplierUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "finance_manager")),
):
    supplier = (
        db.query(Supplier)
        .filter(
            Supplier.supplier_id == supplier_id,
            Supplier.company_id == current_user.company_id,
        )
        .first()
    )
    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Supplier '{supplier_id}' not found",
        )

    update_data = supplier_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(supplier, field, value)

    db.commit()
    db.refresh(supplier)
    return supplier


@router.delete(
    "/{supplier_id}",
    response_model=SupplierRead,
    summary="Soft Delete Supplier",
    description="Soft-deletes a supplier by setting is_active=false. Requires 'admin' role.",
)
def delete_supplier(
    supplier_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    supplier = (
        db.query(Supplier)
        .filter(
            Supplier.supplier_id == supplier_id,
            Supplier.company_id == current_user.company_id,
        )
        .first()
    )
    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Supplier '{supplier_id}' not found",
        )

    supplier.is_active = False
    db.commit()
    db.refresh(supplier)
    return supplier
