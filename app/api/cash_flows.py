from datetime import date, timedelta
from decimal import Decimal
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user, require_roles
from app.models.audit_log import AuditLog
from app.models.cash_flow import CashFlow
from app.models.user import User
from app.schemas.cash_flow import (
    CashFlowCreate,
    CashFlowPeriodSummary,
    CashFlowRead,
    CashFlowSummary,
    CashFlowUpdate,
)
from app.schemas.common import PaginatedResponse, PaginationParams

router = APIRouter(prefix="/cash-flows", tags=["Cash Flows"])


def _log_audit(
    db: Session,
    user_id: Optional[int],
    action: str,
    entity_type: str,
    entity_id: str,
    payload: dict,
) -> None:
    audit = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        payload=payload,
    )
    db.add(audit)


@router.get(
    "",
    response_model=PaginatedResponse[CashFlowRead],
    summary="List Cash Flows",
    description="Retrieve paginated daily cash flow entries scoped to company with optional date range filters.",
)
def list_cash_flows(
    from_date: Optional[date] = Query(None, description="Filter cash flows on or after date"),
    to_date: Optional[date] = Query(None, description="Filter cash flows on or before date"),
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(CashFlow)

    if current_user.company_id:
        query = query.filter(CashFlow.company_id == current_user.company_id)

    if from_date is not None:
        query = query.filter(CashFlow.date >= from_date)

    if to_date is not None:
        query = query.filter(CashFlow.date <= to_date)

    total = query.count()
    items = (
        query.order_by(CashFlow.date.desc(), CashFlow.id.desc())
        .offset(pagination.offset)
        .limit(pagination.limit)
        .all()
    )

    return PaginatedResponse(
        items=[CashFlowRead.model_validate(cf) for cf in items],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get(
    "/latest",
    response_model=CashFlowRead,
    summary="Get Latest Cash Flow",
    description="Retrieve the most recent cash flow record for the current user's company.",
)
def get_latest_cash_flow(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(CashFlow)
    if current_user.company_id:
        query = query.filter(CashFlow.company_id == current_user.company_id)

    latest = query.order_by(CashFlow.date.desc()).first()
    if not latest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No cash flow records found for company",
        )

    return CashFlowRead.model_validate(latest)


@router.get(
    "/summary",
    response_model=CashFlowSummary,
    summary="Get Cash Flow Summary",
    description="Calculates 7-day and 30-day cash flow metrics (total inflow, outflow, net cash flow, and count of days with liquidity_gap > 0).",
)
def get_cash_flows_summary(
    as_of_date: Optional[date] = Query(None, description="Optional reference date (defaults to latest available date)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(CashFlow)
    if current_user.company_id:
        query = query.filter(CashFlow.company_id == current_user.company_id)

    ref_date = as_of_date
    if ref_date is None:
        max_date = query.with_entities(func.max(CashFlow.date)).scalar()
        ref_date = max_date or date.today()

    start_7 = ref_date - timedelta(days=6)
    start_30 = ref_date - timedelta(days=29)

    # 7-day metrics
    rows_7 = (
        query.filter(CashFlow.date >= start_7, CashFlow.date <= ref_date)
        .all()
    )
    total_inflow_7 = sum((r.inflow_actual for r in rows_7), Decimal("0.00"))
    total_outflow_7 = sum((r.outflow_actual for r in rows_7), Decimal("0.00"))
    net_7 = sum((r.net_cash_flow for r in rows_7), Decimal("0.00"))
    gap_days_7 = sum(1 for r in rows_7 if r.liquidity_gap > Decimal("0.00"))

    # 30-day metrics
    rows_30 = (
        query.filter(CashFlow.date >= start_30, CashFlow.date <= ref_date)
        .all()
    )
    total_inflow_30 = sum((r.inflow_actual for r in rows_30), Decimal("0.00"))
    total_outflow_30 = sum((r.outflow_actual for r in rows_30), Decimal("0.00"))
    net_30 = sum((r.net_cash_flow for r in rows_30), Decimal("0.00"))
    gap_days_30 = sum(1 for r in rows_30 if r.liquidity_gap > Decimal("0.00"))

    return CashFlowSummary(
        as_of_date=ref_date,
        last_7_days=CashFlowPeriodSummary(
            start_date=start_7,
            end_date=ref_date,
            total_inflow=total_inflow_7,
            total_outflow=total_outflow_7,
            net_cash_flow=net_7,
            days_with_liquidity_gap=gap_days_7,
        ),
        last_30_days=CashFlowPeriodSummary(
            start_date=start_30,
            end_date=ref_date,
            total_inflow=total_inflow_30,
            total_outflow=total_outflow_30,
            net_cash_flow=net_30,
            days_with_liquidity_gap=gap_days_30,
        ),
    )


@router.post(
    "",
    response_model=CashFlowRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record Cash Flow",
    description="Record a new daily cash flow entry. Validates that closing_balance = opening_balance + net and net = inflow - outflow. Enforces unique (company_id, date).",
)
def create_cash_flow(
    cf_in: CashFlowCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "finance_manager")),
):
    target_company_id = cf_in.company_id or current_user.company_id or 1

    # Check for duplicate date for company
    existing = (
        db.query(CashFlow)
        .filter(CashFlow.company_id == target_company_id, CashFlow.date == cf_in.date)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cash flow record for company {target_company_id} and date '{cf_in.date}' already exists",
        )

    # Validate math strictly
    expected_net = cf_in.inflow_actual - cf_in.outflow_actual
    if abs(cf_in.net_cash_flow - expected_net) > Decimal("0.01"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"net_cash_flow must equal inflow_actual - outflow_actual ({expected_net})",
        )

    expected_closing = cf_in.opening_balance + cf_in.net_cash_flow
    if abs(cf_in.closing_balance - expected_closing) > Decimal("0.01"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"closing_balance must equal opening_balance + net_cash_flow ({expected_closing})",
        )

    cf = CashFlow(
        company_id=target_company_id,
        date=cf_in.date,
        inflow_actual=cf_in.inflow_actual,
        outflow_actual=cf_in.outflow_actual,
        net_cash_flow=cf_in.net_cash_flow,
        opening_balance=cf_in.opening_balance,
        closing_balance=cf_in.closing_balance,
        outstanding_receivables=cf_in.outstanding_receivables,
        min_cash_buffer=cf_in.min_cash_buffer,
        liquidity_gap=cf_in.liquidity_gap,
    )
    db.add(cf)

    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cash flow record for company {target_company_id} and date '{cf_in.date}' already exists",
        )

    _log_audit(
        db=db,
        user_id=current_user.id,
        action="create",
        entity_type="cash_flow",
        entity_id=str(cf.id),
        payload={
            "company_id": target_company_id,
            "date": cf.date.isoformat(),
            "inflow": str(cf.inflow_actual),
            "outflow": str(cf.outflow_actual),
            "net": str(cf.net_cash_flow),
        },
    )

    db.commit()
    db.refresh(cf)
    return CashFlowRead.model_validate(cf)


@router.patch(
    "/{cash_flow_id}",
    response_model=CashFlowRead,
    summary="Update Cash Flow",
    description="Update an existing cash flow record. Validates balance math consistency.",
)
def update_cash_flow(
    cash_flow_id: int,
    cf_update: CashFlowUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "finance_manager")),
):
    query = db.query(CashFlow).filter(CashFlow.id == cash_flow_id)
    if current_user.company_id:
        query = query.filter(CashFlow.company_id == current_user.company_id)

    cf = query.first()
    if not cf:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cash flow '{cash_flow_id}' not found",
        )

    # Compute effective values
    eff_inflow = cf_update.inflow_actual if cf_update.inflow_actual is not None else cf.inflow_actual
    eff_outflow = cf_update.outflow_actual if cf_update.outflow_actual is not None else cf.outflow_actual
    eff_net = cf_update.net_cash_flow if cf_update.net_cash_flow is not None else cf.net_cash_flow
    eff_opening = cf_update.opening_balance if cf_update.opening_balance is not None else cf.opening_balance
    eff_closing = cf_update.closing_balance if cf_update.closing_balance is not None else cf.closing_balance

    expected_net = eff_inflow - eff_outflow
    if abs(eff_net - expected_net) > Decimal("0.01"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"net_cash_flow ({eff_net}) must equal inflow_actual ({eff_inflow}) - outflow_actual ({eff_outflow}) = {expected_net}",
        )

    expected_closing = eff_opening + eff_net
    if abs(eff_closing - expected_closing) > Decimal("0.01"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"closing_balance ({eff_closing}) must equal opening_balance ({eff_opening}) + net_cash_flow ({eff_net}) = {expected_closing}",
        )

    old_values = {
        "inflow_actual": str(cf.inflow_actual),
        "outflow_actual": str(cf.outflow_actual),
        "net_cash_flow": str(cf.net_cash_flow),
        "opening_balance": str(cf.opening_balance),
        "closing_balance": str(cf.closing_balance),
    }

    if cf_update.inflow_actual is not None:
        cf.inflow_actual = cf_update.inflow_actual
    if cf_update.outflow_actual is not None:
        cf.outflow_actual = cf_update.outflow_actual
    if cf_update.net_cash_flow is not None:
        cf.net_cash_flow = cf_update.net_cash_flow
    if cf_update.opening_balance is not None:
        cf.opening_balance = cf_update.opening_balance
    if cf_update.closing_balance is not None:
        cf.closing_balance = cf_update.closing_balance
    if cf_update.outstanding_receivables is not None:
        cf.outstanding_receivables = cf_update.outstanding_receivables
    if cf_update.min_cash_buffer is not None:
        cf.min_cash_buffer = cf_update.min_cash_buffer
    if cf_update.liquidity_gap is not None:
        cf.liquidity_gap = cf_update.liquidity_gap

    new_values = {
        "inflow_actual": str(cf.inflow_actual),
        "outflow_actual": str(cf.outflow_actual),
        "net_cash_flow": str(cf.net_cash_flow),
        "opening_balance": str(cf.opening_balance),
        "closing_balance": str(cf.closing_balance),
    }

    _log_audit(
        db=db,
        user_id=current_user.id,
        action="update",
        entity_type="cash_flow",
        entity_id=str(cf.id),
        payload={"previous": old_values, "changes": new_values},
    )

    db.commit()
    db.refresh(cf)
    return CashFlowRead.model_validate(cf)


@router.delete(
    "/{cash_flow_id}",
    status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
    summary="Delete Cash Flow (Forbidden)",
    description="Hard deletion of cash flows is prohibited for audit trail integrity.",
)
def delete_cash_flow(cash_flow_id: int):
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="Hard deletion of cash flows is not permitted.",
    )
