import logging
import math
import uuid
from fastapi import APIRouter, HTTPException
from typing import Any, List
from pydantic import BaseModel
from sqlmodel import Session, select
from decimal import Decimal
from app.api.deps import SessionDep, CurrentUser
from app.services.user_credit_service import transfer_credits
from app.models import Campaign, User
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

class SendCreditsRequest(BaseModel):
    recipientType: str | None = "individual"
    amount: float
    recipient: str
    message: str | None = None
    groupName: str | None = None
    organizationId: str | None = None

class RecipientData(BaseModel):
    identifier: str
    amount: float

class BulkDistributionRequest(BaseModel):
    totalAmount: float
    distributionType: str
    recipients: List[RecipientData]
    groupName: str | None = None
    purpose: str | None = None
    organizationId: str | None = None

@router.post("/send")
async def send_credits(
    data: SendCreditsRequest,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """
    Send credits to a single recipient
    """
    # recipient is identifier (email or tag)
    # Convert Amount (Naira) to Credits
    # Formula: Credits = Naira / Rate
    credits_amount = Decimal(str(math.ceil(data.amount / settings.NAIRA_TO_CREDIT_RATE)))
    
    if credits_amount <= 0:
        raise HTTPException(status_code=400, detail="Amount too small to convert to credits")

    try:
        if data.organizationId:
            from app.services.user_credit_service import get_user_by_email_or_tag
            from app.services.organization_credit_service import OrganizationCreditService
            
            # Logic for Org -> Personal User
            recipient = get_user_by_email_or_tag(session, data.recipient)
            if not recipient:
                raise HTTPException(status_code=404, detail=f"User not found: {data.recipient}")

            # Use OrganizationCreditService.share_credits for org context to ensure history logging
            OrganizationCreditService.share_credits(
                session=session,
                org_id=uuid.UUID(data.organizationId),
                member_id=recipient.id,
                amount=credits_amount,
                admin_id=current_user.id,
                description=data.message or f"Bulk Send: {data.groupName}",
                commit=True
            )
            result = {"success": True}
        else:
            result = transfer_credits(
                session=session,
                sender=current_user,
                recipient_identifier=data.recipient[1:] if data.recipient.startswith("@") else data.recipient,
                amount=credits_amount,
                message=data.message,
                reference_name=data.groupName
            )

        # Update campaign if groupName provided
        if data.groupName:
            campaign = session.exec(select(Campaign).where(
                Campaign.user_id == current_user.id,
                Campaign.name == data.groupName
            )).first()

            if campaign:
                campaign.total_distributed += Decimal(str(credits_amount))
                campaign.spent_naira += Decimal(str(data.amount))
                if campaign.amount > 0:
                    campaign.progress = min(100, int((campaign.spent_naira / campaign.amount) * 100))
                session.add(campaign)
                session.commit()

        return {"success": True, "message": "Credits sent successfully", "transaction": result}
    except ValueError as e:
        logger.error(f"Transfer credits value error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Transfer credits unexpected error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/bulk-distribution")
async def bulk_distribution(
    data: BulkDistributionRequest,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """
    Bulk distribute credits and update campaign metrics if applicable
    """
    successful = []
    failed = []
    total_distributed_credits = 0
    total_spent_naira = 0

    campaign = None
    if data.groupName:
        campaign = session.exec(select(Campaign).where(
            Campaign.user_id == current_user.id,
            Campaign.name == data.groupName
        )).first()

    for r in data.recipients:
        try:
            # removing @ just in case
            identifier = r.identifier[1:].strip() if r.identifier.strip().startswith("@") else r.identifier.strip()
            
            credits_amount = Decimal(str(math.ceil(r.amount / settings.NAIRA_TO_CREDIT_RATE)))
            
            if credits_amount <= 0:
                failed.append({"identifier": identifier, "error": "Amount too small"})
                continue

            if data.organizationId:
                from app.services.user_credit_service import get_user_by_email_or_tag
                from app.services.organization_credit_service import OrganizationCreditService
                
                recipient = get_user_by_email_or_tag(session, identifier)
                
                if recipient:
                    OrganizationCreditService.share_credits(
                        session=session,
                        org_id=uuid.UUID(data.organizationId),
                        member_id=recipient.id,
                        amount=credits_amount,
                        admin_id=current_user.id,
                        description=data.purpose or f"Bulk Distribution: {data.groupName}",
                        commit=True
                    )
                else:
                    failed.append({"identifier": identifier, "error": "User not found"})
                    continue
            else:
                transfer_credits(
                    session=session,
                    sender=current_user,
                    recipient_identifier=identifier,
                    amount=credits_amount,
                    message=data.purpose,
                    reference_name=data.groupName,
                    transaction_type_override="bulk_transfer_out"
                )
            successful.append(identifier)
            total_distributed_credits += credits_amount
            total_spent_naira += r.amount
        except Exception as e:
            logger.error(f"Bulk transfer failed for {r.identifier}: {e}")
            failed.append({"identifier": r.identifier, "error": str(e)})

    # Update campaign analytics if found
    if campaign and len(successful) > 0:
        campaign.total_distributed += Decimal(str(total_distributed_credits))
        campaign.spent_naira += Decimal(str(total_spent_naira))
        
        # Calculate progress: If campaign.amount is total Naira budget
        if campaign.amount > 0:
            campaign.progress = min(100, int((campaign.spent_naira / campaign.amount) * 100))
        
        session.add(campaign)
        session.commit()

    return {
        "success": True, 
        "message": f"Processed {len(successful)} recipients", 
        "successfulRecipients": len(successful), 
        "failedRecipients": len(failed), 
        "failures": failed
    }
