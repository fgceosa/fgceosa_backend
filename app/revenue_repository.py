"""
Revenue Repository - Handles complex aggregated queries for the platform revenue dashboard.
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from decimal import Decimal

from sqlmodel import Session, select, func, and_
from sqlalchemy import extract, desc, text
import calendar

from app.models import (
    TopUp, 
    TopUpStatus, 
    APIRequest, 
    Organization, 
    Workspace, 
    User, 
    CreditTransaction,
    Project,
    AIModel,
    AIProvider,
    PlatformSettings
)
from app.core.config import settings

def get_admin_revenue_dashboard(*, session: Session, period: str = "month") -> Dict[str, Any]:
    """
    Fetch all data required for the Revenue Overview page.
    """
    now = datetime.now(timezone.utc)
    
    # Calculate start date based on period
    if period == "week":
        start_date = now - timedelta(days=7)
    elif period == "month":
        start_date = now - timedelta(days=30)
    elif period == "year":
        start_date = now - timedelta(days=365)
    else:
        start_date = now - timedelta(days=30) # Default to month if period is invalid

    # Fetch dynamic platform settings
    platform_settings = session.exec(select(PlatformSettings)).first()
    
    # Defaults
    exchange_rate = 1650.0 
    markup_percent = 15.0
    
    if platform_settings and hasattr(platform_settings, 'payments') and platform_settings.payments:
        pmts = platform_settings.payments
        exchange_rate = float(pmts.get("nairaToCreditRate") if pmts.get("nairaToCreditRate") is not None else 1650.0)
        markup_percent = float(pmts.get("defaultMarkup") if pmts.get("defaultMarkup") is not None else 15.0)
    
    # 1. KPI Metrics
    
    # Total Revenue (Lifetime) - Cash Inflow (Top-ups)
    total_revenue_val = float(session.exec(
        select(func.coalesce(func.sum(TopUp.amount_naira), 0)).where(TopUp.status == TopUpStatus.COMPLETED.value)
    ).one())

    # Calculate Model Costs (What the platform pays to providers)
    # Since APIRequest.cost includes the markup, we divide it back
    markup_factor = 1 + (markup_percent / 100.0)
    total_user_usage_usd = float(session.exec(select(func.coalesce(func.sum(APIRequest.cost), 0))).one())
    
    total_cost_usd = total_user_usage_usd / markup_factor
    total_model_costs_val = total_cost_usd * exchange_rate # Platform expense in Naira

    # Usage Revenue (What users are charged in Naira equivalent)
    total_usage_revenue_naira = total_user_usage_usd * exchange_rate

    # Net Profit (Profit from consumption)
    net_profit_val = total_usage_revenue_naira - total_model_costs_val
    
    # Outstanding Payments (Pending TopUps)
    outstanding_payments_val = float(session.exec(
        select(func.coalesce(func.sum(TopUp.amount_naira), 0)).where(TopUp.status == TopUpStatus.PENDING.value)
    ).one())

    # Credits Sold (Lifetime)
    credits_sold_val = float(session.exec(
        select(func.coalesce(func.sum(TopUp.ai_credits), 0)).where(TopUp.status == TopUpStatus.COMPLETED.value)
    ).one())

    # Credits Consumed (Lifetime)
    credits_consumed_val = total_user_usage_usd # Because 1 credit = 1 USD in our logic

    # Active Organizations
    active_organizations_val = session.exec(select(func.count(Organization.id)).where(Organization.is_active == True)).one()

    # Calculate Margin (Profit / Usage Revenue)
    margin_val = (net_profit_val / total_usage_revenue_naira * 100) if total_usage_revenue_naira > 0 else 0

    kpi = {
        "totalRevenue": {"amount": total_revenue_val, "change": 0, "trend": "up", "type": "positive", "label": "Cash In"},
        "modelCosts": {"amount": total_model_costs_val, "change": 0, "trend": "up", "type": "neutral", "label": "Expenses"},
        "netProfit": {"amount": net_profit_val, "change": 0, "trend": "up", "type": "positive", "label": "Profit"},
        "outstandingPayments": {"amount": outstanding_payments_val, "change": 0, "trend": "down", "type": "warning", "label": "Pending"},
        "creditsSold": {"amount": credits_sold_val, "change": 0, "trend": "up", "type": "positive", "label": "Total"},
        "creditsConsumed": {"amount": credits_consumed_val, "change": 0, "trend": "up", "type": "neutral", "label": "Total"},
        "grossMargin": {"amount": margin_val, "change": 0, "trend": "up", "type": "positive", "label": "Margin"},
        "activeOrganizations": {"amount": active_organizations_val, "change": 0, "trend": "up", "type": "positive", "label": "Active"}
    }

    # 2. Chart Data (Monthly trends for last 12 months)
    chart_data = []
    for i in range(6): # Last 6 months for focus
        month_offset = i
        # Calculate month date
        month_date = (now.replace(day=1) - timedelta(days=month_offset * 30)).replace(day=1)
        target_month = month_date.month
        target_year = month_date.year
        
        last_day = calendar.monthrange(target_year, target_month)[1]
        m_start = datetime(target_year, target_month, 1, tzinfo=timezone.utc)
        m_end = datetime(target_year, target_month, last_day, 23, 59, 59, tzinfo=timezone.utc)

        # m_rev (cash inflow from top-ups) is not used in the chart data anymore, but kept for reference if needed elsewhere
        m_rev = float(session.exec(
            select(func.coalesce(func.sum(TopUp.amount_naira), 0)).where(
                and_(TopUp.status == TopUpStatus.COMPLETED.value, TopUp.created_at >= m_start, TopUp.created_at <= m_end)
            )
        ).one())

        m_user_usage_usd = float(session.exec(
            select(func.coalesce(func.sum(APIRequest.cost), 0)).where(
                and_(APIRequest.created_at >= m_start, APIRequest.created_at <= m_end)
            )
        ).one())
        
        m_cost_naira = (m_user_usage_usd / markup_factor) * exchange_rate
        m_usage_rev_naira = m_user_usage_usd * exchange_rate

        chart_data.append({
            "month": m_start.strftime("%b"),
            "revenue": m_usage_rev_naira,
            "costs": m_cost_naira,
            "trend": m_usage_rev_naira - m_cost_naira
        })
    chart_data.reverse()

    # 3. Revenue by Workspace
    workspace_data = []
    top_workspaces = session.exec(
        select(Workspace).order_by(desc(Workspace.credits_balance)).limit(10)
    ).all()
    
    total_ws_revenue = 0
    for ws in top_workspaces:
        ws_rev = float(session.exec(
            select(func.coalesce(func.sum(TopUp.amount_naira), 0)).where(
                and_(TopUp.workspace_id == ws.id, TopUp.status == TopUpStatus.COMPLETED.value)
            )
        ).one())
        total_ws_revenue += ws_rev
        workspace_data.append({
            "id": str(ws.id),
            "name": ws.name,
            "revenue": ws_rev,
            "share": 0
        })
    
    if total_ws_revenue > 0:
        for ws in workspace_data:
            ws["share"] = round((ws["revenue"] / total_ws_revenue) * 100, 1)

    # 4. Top Models
    top_models_stmt = (
        select(APIRequest.model, func.count(APIRequest.id).label("usage"), func.sum(APIRequest.cost).label("cost"))
        .group_by(APIRequest.model)
        .order_by(desc("usage"))
        .limit(6)
    )
    models_usage = session.exec(top_models_stmt).all()
    top_models = []
    for model_name, usage, cost in models_usage:
        # Use markup to calculate estimated revenue for this model usage
        markup_multiplier = 1 + (markup_percent / 100.0)
        model_revenue = float(cost or 0) * markup_multiplier * exchange_rate
        top_models.append({
            "id": model_name,
            "model": model_name,
            "provider": model_name.split("/")[0].title() if "/" in model_name else "AI",
            "revenue": model_revenue,
            "usage": usage,
            "growth": 12.5
        })

    # 5. Recent Transactions
    recent_trx_stmt = (
        select(TopUp, User)
        .join(User, TopUp.user_id == User.id)
        .order_by(desc(TopUp.created_at))
        .limit(10)
    )
    raw_trx = session.exec(recent_trx_stmt).all()
    recent_transactions = []
    for t, u in raw_trx:
        recent_transactions.append({
            "id": str(t.id),
            "date": t.created_at.strftime("%Y-%m-%d %H:%M"),
            "organization": u.organization_name or u.full_name or u.email,
            "amount": float(t.amount_naira),
            "type": "credit_purchase",
            "status": str(t.status.value if hasattr(t.status, 'value') else t.status).title()
        })

    # 6. Revenue Source Analysis
    source_stmt = (
        select(TopUp.payment_method, func.sum(TopUp.amount_naira))
        .where(TopUp.status == TopUpStatus.COMPLETED.value)
        .group_by(TopUp.payment_method)
    )
    sources = session.exec(source_stmt).all()
    revenue_by_source = []
    total_rev_src = sum(float(v) for k, v in sources) if sources else 0
    for method, amt in sources:
        revenue_by_source.append({
            "source": str(method).replace("_", " ").title() if method else "Other",
            "amount": float(amt),
            "percentage": round((float(amt) / total_rev_src) * 100, 1) if total_rev_src > 0 else 0
        })
    if not revenue_by_source:
        revenue_by_source = [{"source": "Direct Payment", "amount": 0, "percentage": 0}]

    # 7. Provider Analysis
    provider_stmt = (
        select(APIRequest.model, func.sum(APIRequest.cost))
        .group_by(APIRequest.model)
    )
    prov_data = session.exec(provider_stmt).all()
    cost_by_provider_map = {}
    for model, cost in prov_data:
        provider = model.split("/")[0] if "/" in model else "Other"
        if provider not in cost_by_provider_map:
            cost_by_provider_map[provider] = {"cost": 0, "usage": 0}
        cost_by_provider_map[provider]["cost"] += float(cost)
        cost_by_provider_map[provider]["usage"] += 1

    cost_by_provider = []
    for prov, values in cost_by_provider_map.items():
        markup_multiplier = 1 + (markup_percent / 100.0)
        prov_rev = values["cost"] * markup_multiplier * exchange_rate
        prov_cost = values["cost"] * exchange_rate
        cost_by_provider.append({
            "provider": prov.title(),
            "creditsConsumed": values["cost"],
            "cost": prov_cost,
            "revenue": prov_rev,
            "margin": round(((prov_rev - prov_cost) / prov_rev * 100), 1) if prov_rev > 0 else 100
        })

    # 8. Top Spenders
    top_spenders_stmt = (
        select(User, func.sum(TopUp.amount_naira).label("total_spend"), func.sum(TopUp.ai_credits).label("total_credits"))
        .join(TopUp, User.id == TopUp.user_id)
        .where(TopUp.status == TopUpStatus.COMPLETED.value)
        .group_by(User.id)
        .order_by(text("total_spend DESC"))
        .limit(5)
    )
    spenders = session.exec(top_spenders_stmt).all()
    top_spenders = []
    for u, spend, credits in spenders:
        top_spenders.append({
            "organization": u.organization_name or u.full_name or u.email,
            "spend": float(spend),
            "creditsUsed": float(credits),
            "lastActivity": "Just now",
            "status": "Active"
        })

    # 9. Credit Flow
    remaining_credits = float(session.exec(select(func.coalesce(func.sum(User.credits), 0))).one())
    transferred = abs(float(session.exec(
        select(func.coalesce(func.sum(CreditTransaction.amount), 0)).where(CreditTransaction.transaction_type == "transfer")
    ).one()))

    credit_flow = {
        "issued": credits_sold_val,
        "transferred": transferred,
        "consumed": credits_consumed_val,
        "remaining": remaining_credits
    }

    return {
        "kpi": kpi,
        "chartData": chart_data,
        "revenueByWorkspace": workspace_data,
        "topModels": top_models,
        "recentTransactions": recent_transactions,
        "revenueBySource": revenue_by_source,
        "costByProvider": cost_by_provider,
        "topSpenders": top_spenders,
        "creditFlow": credit_flow
    }
