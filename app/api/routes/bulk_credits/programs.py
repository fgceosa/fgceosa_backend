from fastapi import APIRouter, HTTPException, Depends
from typing import Any, List
from sqlmodel import select, func, col
from app.api.deps import SessionDep, CurrentUser
from app.models import Campaign, CampaignCreate, CampaignUpdate, CampaignPublic, CreditTransaction, OrganizationCreditTransaction
from app.core.config import settings
import uuid
from decimal import Decimal

router = APIRouter()

@router.get("/campaigns", response_model=dict)
async def get_campaigns(
    session: SessionDep,
    current_user: CurrentUser,
    page: int = 1,
    page_size: int = 100,
    status: str | None = None,
    organization_id: uuid.UUID | None = None
) -> Any:
    """
    Get list of campaigns/programs
    """
    skip = (page - 1) * page_size
    
    if organization_id:
        filter_clause = (Campaign.organization_id == organization_id)
    else:
        filter_clause = (Campaign.user_id == current_user.id)
        
    query = select(Campaign).where(filter_clause)
    
    if status:
        query = query.where(Campaign.status == status)
        
    query = query.offset(skip).limit(page_size).order_by(col(Campaign.created_at).desc())
    
    campaigns = session.exec(query).all()
    total = session.exec(select(func.count()).select_from(Campaign).where(filter_clause)).one()
    
    return {
        "campaigns": campaigns,
        "total": total
    }

@router.get("/campaigns/{campaign_id}", response_model=CampaignPublic)
async def get_campaign(
    campaign_id: str,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """
    Get a single campaign/program
    """
    try:
        campaign_uuid = uuid.UUID(campaign_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid campaign ID")
        
    campaign = session.get(Campaign, campaign_uuid)
    if not campaign or (campaign.user_id != current_user.id and campaign.organization_id is None):
        # Todo: Verify organization access if it's an organization campaign
        raise HTTPException(status_code=404, detail="Program not found")
        
    return campaign

@router.post("/campaigns", response_model=CampaignPublic)
async def create_campaign(
    campaign_in: CampaignCreate,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """
    Create a new campaign/program
    """
    campaign = Campaign(
        user_id=current_user.id,
        organization_id=campaign_in.organization_id,
        name=campaign_in.name,
        description=campaign_in.description,
        type=campaign_in.type,
        amount=campaign_in.amount,
        recipients=campaign_in.recipients,
        starts_at=campaign_in.starts_at,
        ends_at=campaign_in.ends_at,
        status=campaign_in.status or "active"
    )
    session.add(campaign)
    session.commit()
    session.refresh(campaign)
    return campaign

@router.put("/campaigns/{campaign_id}", response_model=CampaignPublic)
async def update_campaign(
    campaign_id: str,
    campaign_in: CampaignUpdate,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    try:
        campaign_uuid = uuid.UUID(campaign_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid campaign ID")
        
    campaign = session.get(Campaign, campaign_uuid)
    if not campaign or (campaign.user_id != current_user.id and campaign.organization_id is None):
        raise HTTPException(status_code=404, detail="Program not found")
        
    campaign_data = campaign_in.model_dump(exclude_unset=True)
    for key, value in campaign_data.items():
        setattr(campaign, key, value)
    
    session.add(campaign)
    session.commit()
    session.refresh(campaign)
    return campaign

@router.delete("/campaigns/{campaign_id}")
async def delete_campaign(
    campaign_id: str,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    try:
        campaign_uuid = uuid.UUID(campaign_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid campaign ID")
        
    campaign = session.get(Campaign, campaign_uuid)
    if not campaign or (campaign.user_id != current_user.id and campaign.organization_id is None):
        raise HTTPException(status_code=404, detail="Program not found")
        
    session.delete(campaign)
    session.commit()
    return {"success": True, "message": "Program deleted successfully"}

@router.get("/campaigns/{campaign_id}/analytics")
async def get_campaign_analytics(
    campaign_id: str,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """
    Get detailed analytics for a campaign
    """
    try:
        campaign_uuid = uuid.UUID(campaign_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid campaign ID")
        
    campaign = session.get(Campaign, campaign_uuid)
    if not campaign or (campaign.user_id != current_user.id and campaign.organization_id is None):
        raise HTTPException(status_code=404, detail="Program not found")
        
    # Get recent transactions linked to this campaign
    if campaign.organization_id:
        tx_model = OrganizationCreditTransaction
        tx_filter = (OrganizationCreditTransaction.organization_id == campaign.organization_id)
        # For orgs, we use description search as a fallback for reference_id
        campaign_match_filter = (OrganizationCreditTransaction.description.contains(campaign.name))
    else:
        tx_model = CreditTransaction
        tx_filter = (CreditTransaction.user_id == current_user.id)
        campaign_match_filter = (CreditTransaction.reference_id == campaign.name)
        
    transactions_query = select(tx_model).where(
        tx_filter,
        campaign_match_filter
    ).order_by(col(tx_model.created_at).desc()).limit(10)
    
    recent_transactions = session.exec(transactions_query).all()
    
    # Calculate unique recipients for this program
    actual_recipients = session.exec(
        select(func.count(func.distinct(tx_model.description))).where(
            tx_filter,
            campaign_match_filter
        )
    ).one() or 0
    
    return {
        "campaign": campaign,
        "analytics": {
            "total_budget": float(campaign.amount),
            "total_spent": float(campaign.spent_naira),
            "total_distributed": float(campaign.total_distributed),
            "remaining_budget": float(campaign.amount - campaign.spent_naira),
            "target_recipients": campaign.recipients,
            "actual_recipients": actual_recipients,
            "progress": campaign.progress,
        },
        "recent_transactions": [
            {
                "id": str(t.id),
                "date": t.created_at.isoformat(),
                "amount": float(abs(t.amount)) * settings.NAIRA_TO_CREDIT_RATE,
                "credits": float(abs(t.amount)),
                "description": t.description
            }
            for t in recent_transactions
        ]
    }

@router.get("/aggregated-analytics")
async def get_aggregated_analytics(
    session: SessionDep,
    current_user: CurrentUser,
    organization_id: uuid.UUID | None = None,
) -> Any:
    """
    Get aggregated analytics across all campaigns/programs
    """
    if organization_id:
        filter_clause = (Campaign.organization_id == organization_id)
        tx_model = OrganizationCreditTransaction
        tx_filter = (OrganizationCreditTransaction.organization_id == organization_id)
    else:
        filter_clause = (Campaign.user_id == current_user.id)
        tx_model = CreditTransaction
        tx_filter = (CreditTransaction.user_id == current_user.id)
        
    query = select(Campaign).where(filter_clause)
    campaigns = session.exec(query).all()
    
    total_budget = sum(c.amount for c in campaigns)
    total_spent = sum(c.spent_naira for c in campaigns)
    total_distributed = sum(c.total_distributed for c in campaigns)
    
    # Calculate actual unique recipients across all programs
    # We look for transactions with a reference_id that matches one of the user's campaign names
    campaign_names = [c.name for c in campaigns]
    total_impacted_users = 0
    if campaign_names:
        if tx_model == OrganizationCreditTransaction:
            # For organizations, we check if description contains any of the campaign names
            # This is complex with SQLModel/SQLAlchemy for multiple names, so we'll simplify or use a loop if needed
            # For now, let's use a combined OR filter for descriptions
            from sqlalchemy import or_
            desc_filters = [OrganizationCreditTransaction.description.contains(name) for name in campaign_names]
            total_impacted_users = session.exec(
                select(func.count(func.distinct(OrganizationCreditTransaction.description))).where(
                    tx_filter,
                    or_(*desc_filters)
                )
            ).one() or 0
        else:
            total_impacted_users = session.exec(
                select(func.count(func.distinct(CreditTransaction.description))).where(
                    tx_filter,
                    col(CreditTransaction.reference_id).in_(campaign_names)
                )
            ).one() or 0
    
    # Map programs with their actual recipient counts
    program_impacts = {}
    if campaign_names:
        if tx_model == OrganizationCreditTransaction:
            # We'll have to approximate this for orgs without reference_id field
            # For each campaign, count recipients
            for name in campaign_names:
                count = session.exec(
                    select(func.count(func.distinct(OrganizationCreditTransaction.description))).where(
                        tx_filter,
                        OrganizationCreditTransaction.description.contains(name)
                    )
                ).one() or 0
                program_impacts[name] = count
        else:
            impacts_query = session.exec(
                select(CreditTransaction.reference_id, func.count(func.distinct(CreditTransaction.description))).where(
                    tx_filter,
                    col(CreditTransaction.reference_id).in_(campaign_names)
                ).group_by(CreditTransaction.reference_id)
            ).all()
            program_impacts = {name: count for name, count in impacts_query}
    
    # Category breakdown
    categories = {}
    for c in campaigns:
        cat = c.type or "General"
        if cat not in categories:
            categories[cat] = {
                "count": 0,
                "budget": Decimal("0.00"),
                "spent": Decimal("0.00")
            }
        categories[cat]["count"] += 1
        categories[cat]["budget"] += c.amount
        categories[cat]["spent"] += c.spent_naira

    return {
        "summary": {
            "total_programs": len(campaigns),
            "total_budget": float(total_budget),
            "total_spent": float(total_spent),
            "total_distributed": float(total_distributed),
            "total_recipients": total_impacted_users,
            "target_recipients": sum(c.recipients for c in campaigns),
            "overall_progress": int((total_spent / total_budget * 100)) if total_budget > 0 else 0
        },
        "categories": [
            {
                "name": name,
                "count": stats["count"],
                "budget": float(stats["budget"]),
                "spent": float(stats["spent"]),
                "progress": int((stats["spent"] / stats["budget"] * 100)) if stats["budget"] > 0 else 0
            }
            for name, stats in categories.items()
        ],
        "programs": [
            {
                "id": str(c.id),
                "name": c.name,
                "type": c.type,
                "status": c.status,
                "progress": c.progress,
                "spent": float(c.spent_naira),
                "budget": float(c.amount),
                "actual_recipients": program_impacts.get(c.name, 0),
                "target_recipients": c.recipients
            }
            for c in campaigns
        ]
    }
