import uuid
from fastapi import APIRouter
from typing import Any
from sqlmodel import select, func, col
from datetime import datetime
from app.api.deps import SessionDep, CurrentUser
from app.models import CreditTransaction, OrganizationCreditTransaction
from app.core.config import settings

router = APIRouter()

@router.get("/transactions")
async def get_bulk_transactions(
    session: SessionDep,
    current_user: CurrentUser,
    page: int = 1,
    page_size: int = 50,
    search: str | None = None,
    type: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    organization_id: uuid.UUID | None = None,
) -> Any:
    """
    Get credit transactions for the bulk credit page
    """
    # Calculate skipping
    skip = (page - 1) * page_size
    
    # 1. Determine context and fetch transactions
    if organization_id:
        # Organization Transactions Context
        # Count total
        count_query = select(func.count()).select_from(OrganizationCreditTransaction).where(
            OrganizationCreditTransaction.organization_id == organization_id
        )
        if type:
            count_query = count_query.where(OrganizationCreditTransaction.transaction_type == type)
        if start_date:
            count_query = count_query.where(OrganizationCreditTransaction.created_at >= start_date)
        if end_date:
            if end_date.hour == 0 and end_date.minute == 0 and end_date.second == 0:
                from datetime import time
                end_date = datetime.combine(end_date.date(), time(23, 59, 59, 999999))
            count_query = count_query.where(OrganizationCreditTransaction.created_at <= end_date)
        if search:
            count_query = count_query.where(OrganizationCreditTransaction.description.contains(search))
            
        total = session.exec(count_query).one()
        
        # Get data
        data_query = select(OrganizationCreditTransaction).where(
            OrganizationCreditTransaction.organization_id == organization_id
        )
        if type:
            data_query = data_query.where(OrganizationCreditTransaction.transaction_type == type)
        if start_date:
            data_query = data_query.where(OrganizationCreditTransaction.created_at >= start_date)
        if end_date:
            data_query = data_query.where(OrganizationCreditTransaction.created_at <= end_date)
        if search:
            data_query = data_query.where(OrganizationCreditTransaction.description.contains(search))
            
        transactions = session.exec(
            data_query.offset(skip).limit(page_size).order_by(col(OrganizationCreditTransaction.created_at).desc())
        ).all()
        
        formatted_transactions = [
            {
                "id": str(t.id),
                "date": t.created_at.isoformat() if t.created_at else None,
                "type": (
                    "Distributed" if t.transaction_type == "allocation" else
                    "Top Up" if t.transaction_type == "topup" else
                    "Platform Usage" if t.transaction_type == "usage" else
                    t.transaction_type.replace("_", " ").title()
                ),
                "amount": abs(float(t.amount)) * settings.NAIRA_TO_CREDIT_RATE,
                "credits": abs(float(t.amount)),
                "recipient": t.description.split(" to ")[1].split(":")[0].strip() if " to " in t.description else "Organization",
                "status": "Completed",
                "badgeType": "success",
            }
            for t in transactions
        ]
    else:
        # User Transactions Context
        # Count total
        count_query = select(func.count()).select_from(CreditTransaction).where(
            CreditTransaction.user_id == current_user.id
        )
        if type:
            count_query = count_query.where(CreditTransaction.transaction_type == type)
        if start_date:
            count_query = count_query.where(CreditTransaction.created_at >= start_date)
        if end_date:
            if end_date.hour == 0 and end_date.minute == 0 and end_date.second == 0:
                from datetime import time
                end_date = datetime.combine(end_date.date(), time(23, 59, 59, 999999))
            count_query = count_query.where(CreditTransaction.created_at <= end_date)
        if search:
            count_query = count_query.where(CreditTransaction.description.contains(search))
            
        total = session.exec(count_query).one()
        
        # Get data
        data_query = select(CreditTransaction).where(CreditTransaction.user_id == current_user.id)
        if type:
            data_query = data_query.where(CreditTransaction.transaction_type == type)
        if start_date:
            data_query = data_query.where(CreditTransaction.created_at >= start_date)
        if end_date:
            data_query = data_query.where(CreditTransaction.created_at <= end_date)
        if search:
            data_query = data_query.where(CreditTransaction.description.contains(search))
            
        transactions = session.exec(
            data_query.offset(skip).limit(page_size).order_by(col(CreditTransaction.created_at).desc())
        ).all()
        
        formatted_transactions = [
            {
                "id": str(t.id),
                "date": t.created_at.isoformat() if t.created_at else None,
                "type": (
                    "Bulk Send" if t.transaction_type == "bulk_transfer_out" or "Bulk" in (t.reference_id or "") else
                    "Sent" if t.transaction_type == "transfer_out" else
                    "Received" if t.transaction_type == "transfer_in" else
                    "Purchase" if t.transaction_type == "purchase" else
                    "Platform Usage" if t.transaction_type == "usage" else
                    t.transaction_type.replace("_", " ").title() if t.transaction_type else "Unknown"
                ),
                "amount": abs(float(t.amount)) * settings.NAIRA_TO_CREDIT_RATE,
                "credits": abs(float(t.amount)),
                "recipient": t.description.split(" to ")[1].split(":")[0].strip() if " to " in t.description else 
                             (t.description.split(" from ")[1].split(":")[0].strip() if " from " in t.description else "Internal"),
                "status": "Completed", 
                "badgeType": "success",
            }
            for t in transactions
        ]
    
    return {
        "transactions": formatted_transactions,
        "total": total
    }
