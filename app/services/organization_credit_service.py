import uuid
import logging
from datetime import datetime, timezone, timedelta
import sqlalchemy as sa
from decimal import Decimal
from typing import List, Tuple, Optional, Any

from sqlmodel import Session, select, func
from fastapi import HTTPException

from app.models import (
    Organization, 
    OrganizationCreditTransaction, 
    Workspace, 
    WorkspaceUsageTracking, 
    User,
    WalletOwnerType,
    WalletTransactionType,
    APIRequest
)
from app.services.wallet_service import WalletService
from app.schemas.organization_credits import (
    OrganizationCreditBalance,
    OrganizationCreditTransactionPublic,
    WorkspaceUsageBreakdown,
    OrganizationUsageSummary
)

logger = logging.getLogger(__name__)

class OrganizationCreditService:
    @staticmethod
    def get_organization(session: Session, org_id: uuid.UUID) -> Organization:
        org = session.get(Organization, org_id)
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")
        return org

    @staticmethod
    def get_balance(session: Session, org_id: uuid.UUID) -> OrganizationCreditBalance:
        wallet = WalletService.get_or_create_wallet(session, org_id, WalletOwnerType.ORGANIZATION)
        balance = WalletService.get_balance(session, wallet.id)
        
        # Calculate monthly usage (current month) from transactions ledger
        now = datetime.now(timezone.utc)
        start_of_month = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        
        # Sum all usage transactions for the org in the current month
        usage_query = select(func.sum(OrganizationCreditTransaction.amount)).where(
            OrganizationCreditTransaction.organization_id == org_id,
            OrganizationCreditTransaction.transaction_type == "usage",
            OrganizationCreditTransaction.created_at >= start_of_month
        )
        monthly_usage_val = session.exec(usage_query).one() or Decimal("0.0000")
        monthly_usage = abs(monthly_usage_val)
        
        return OrganizationCreditBalance(
            balance=balance,
            monthly_usage=monthly_usage,
            remaining_credits=balance
        )

    @staticmethod
    def list_transactions(
        session: Session, 
        org_id: uuid.UUID, 
        page: int = 1, 
        page_size: int = 20
    ) -> Tuple[List[OrganizationCreditTransactionPublic], int]:
        
        # Count total
        count_query = select(func.count()).where(OrganizationCreditTransaction.organization_id == org_id)
        total = session.exec(count_query).one()
        
        # Get transactions
        query = select(OrganizationCreditTransaction).where(
            OrganizationCreditTransaction.organization_id == org_id
        ).order_by(OrganizationCreditTransaction.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        
        transactions = session.exec(query).all()
        
        result = []
        for tx in transactions:
            # Fetch related names if needed (could be optimized with joins)
            workspace_name = None
            if tx.workspace_id:
                ws = session.get(Workspace, tx.workspace_id)
                if ws:
                    workspace_name = ws.name
            
            user_name = None
            if tx.performed_by:
                user = session.get(User, tx.performed_by)
                if user:
                    user_name = user.full_name or user.email

            result.append(OrganizationCreditTransactionPublic(
                id=tx.id,
                organization_id=tx.organization_id,
                amount=tx.amount,
                balance_after=tx.balance_after,
                transaction_type=tx.transaction_type,
                description=tx.description,
                workspace_id=tx.workspace_id,
                performed_by=tx.performed_by,
                created_at=tx.created_at,
                workspace_name=workspace_name,
                user_name=user_name
            ))
            
        return result, total

    @staticmethod
    def update_workspace_limit(session: Session, workspace_id: uuid.UUID, limit: Decimal) -> Workspace:
        workspace = session.get(Workspace, workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")
        
        workspace.monthly_credit_limit = limit
        session.add(workspace)
        session.commit()
        session.refresh(workspace)
        return workspace

    @staticmethod
    def get_usage_summary(
        session: Session, 
        org_id: uuid.UUID, 
        start_date: datetime,
        end_date: datetime
    ) -> OrganizationUsageSummary:
        
        # 1. Fetch TOTAL organization usage for the period (including unassigned)
        total_usage_query = select(func.sum(OrganizationCreditTransaction.amount)).where(
            OrganizationCreditTransaction.organization_id == org_id,
            OrganizationCreditTransaction.transaction_type == "usage",
            OrganizationCreditTransaction.created_at >= start_date,
            OrganizationCreditTransaction.created_at <= end_date
        )
        total_org_usage_val = session.exec(total_usage_query).first()
        total_org_usage = abs(total_org_usage_val) if total_org_usage_val is not None else Decimal("0.0000")

        workspaces = session.exec(select(Workspace).where(Workspace.organization_id == org_id)).all()
        workspaces_usage = []
        
        # 2. Fetch usage for each specific workspace
        tracked_ws_usage = Decimal("0.0000")
        for ws in workspaces:
            usage_query = select(func.sum(OrganizationCreditTransaction.amount)).where(
                OrganizationCreditTransaction.organization_id == org_id,
                OrganizationCreditTransaction.workspace_id == ws.id,
                OrganizationCreditTransaction.transaction_type == "usage",
                OrganizationCreditTransaction.created_at >= start_date,
                OrganizationCreditTransaction.created_at <= end_date
            )
            val = session.exec(usage_query).first()
            total_usage = abs(val) if val is not None else Decimal("0.0000")
            tracked_ws_usage += total_usage
            
            percentage = 0.0
            if total_org_usage > 0:
                percentage = float(total_usage / total_org_usage) * 100
                
            workspaces_usage.append(WorkspaceUsageBreakdown(
                workspace_id=ws.id,
                workspace_name=ws.name,
                total_usage=total_usage,
                monthly_limit=ws.monthly_credit_limit,
                usage_percentage=percentage,
                breakdown={}  
            ))

        # 3. Add 'Shared/API' category for usage not linked to any workspace
        unassigned_usage = total_org_usage - tracked_ws_usage
        if unassigned_usage > Decimal("0.0001"):  # Significant enough to show
            percentage = float(unassigned_usage / total_org_usage) * 100
            workspaces_usage.append(WorkspaceUsageBreakdown(
                workspace_id=None,
                workspace_name="Shared / API Keys",
                total_usage=unassigned_usage,
                monthly_limit=Decimal("0.0000"),
                usage_percentage=percentage,
                breakdown={}
            ))

        # 4. Calculate Health Metrics (Success Rate, Latency)
        health_req_stmt = select(
            func.count(APIRequest.id).label("total"),
            func.sum(sa.case((APIRequest.status == "success", 1), else_=0)).label("success"),
            func.avg(APIRequest.response_time_ms).label("latency")
        ).where(
            APIRequest.organization_id == org_id,
            APIRequest.created_at >= start_date,
            APIRequest.created_at <= end_date
        )
        health_result = session.exec(health_req_stmt).first()
        
        avg_latency = float(health_result.latency or 0.0) if health_result else 0.0
        total_reqs = health_result.total if health_result else 0
        success_reqs = health_result.success if health_result else 0
        success_rate = (success_reqs / total_reqs * 100) if total_reqs > 0 else 100.0

        # 5. Calculate Daily Usage Trends
        daily_usage = []
        total_api_calls = 0
        
        # Get daily data for the last 12 days
        for i in range(12):
            d_start = end_date - timedelta(days=11-i)
            d_start = d_start.replace(hour=0, minute=0, second=0, microsecond=0)
            d_end = d_start + timedelta(days=1)
            
            daily_stats_stmt = select(
                func.coalesce(func.sum(APIRequest.total_tokens), 0).label("tokens"),
                func.count(APIRequest.id).label("requests")
            ).where(
                APIRequest.organization_id == org_id,
                APIRequest.created_at >= d_start,
                APIRequest.created_at < d_end
            )
            stats = session.exec(daily_stats_stmt).first()
            
            tokens = int(stats.tokens) if stats else 0
            requests = int(stats.requests) if stats else 0
            total_api_calls += requests
            
            daily_usage.append({
                "date": d_start.strftime("%Y-%m-%d"),
                "tokens": tokens,
                "requests": requests
            })

        return OrganizationUsageSummary(
            total_usage=total_org_usage,
            total_api_calls=total_api_calls,
            workspaces_usage=workspaces_usage,
            period_start=start_date,
            period_end=end_date,
            avg_latency=avg_latency,
            success_rate=success_rate,
            daily_usage=daily_usage
        )

    @staticmethod
    def check_workspace_limit(session: Session, workspace_id: uuid.UUID, amount: Decimal):
        """Check if workspace has exceeded its monthly limit"""
        workspace = session.get(Workspace, workspace_id)
        if not workspace or workspace.monthly_credit_limit <= 0:
            return

        now = datetime.now(timezone.utc)
        start_of_month = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        
        # Get current usage
        tracking = session.exec(
            select(WorkspaceUsageTracking).where(
                WorkspaceUsageTracking.workspace_id == workspace_id,
                WorkspaceUsageTracking.billing_period_start == start_of_month
            )
        ).first()
        
        current_usage = tracking.total_usage if tracking else Decimal("0.0000")
        
        if current_usage + amount > workspace.monthly_credit_limit:
             raise HTTPException(
                status_code=403, 
                detail=f"Workspace monthly credit limit exceeded. Limit: {workspace.monthly_credit_limit}, Used: {current_usage}, Required: {amount}"
            )

    @staticmethod
    def track_workspace_usage(
        session: Session, 
        workspace_id: uuid.UUID, 
        org_id: uuid.UUID, 
        amount: Decimal,
        metadata: Optional[dict] = None
    ):
        """Track usage statistics for workspace"""
        now = datetime.now(timezone.utc)
        start_of_month = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        
        # Next month start
        if now.month == 12:
            end_of_month = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            end_of_month = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)

        tracking = session.exec(
            select(WorkspaceUsageTracking).where(
                WorkspaceUsageTracking.workspace_id == workspace_id,
                WorkspaceUsageTracking.billing_period_start == start_of_month
            )
        ).first()
        
        if not tracking:
            tracking = WorkspaceUsageTracking(
                workspace_id=workspace_id,
                organization_id=org_id,
                billing_period_start=start_of_month,
                billing_period_end=end_of_month,
                total_usage=Decimal("0.0000"),
                usage_breakdown={}
            )
            session.add(tracking)
        
        tracking.total_usage += amount
        tracking.updated_at = now
        
        # Update breakdown if metadata provided
        if metadata and tracking.usage_breakdown is not None:
            # Simple merge for now, could be more sophisticated
            current_breakdown = dict(tracking.usage_breakdown)
            for k, v in metadata.items():
                if isinstance(v, (int, float)):
                    current_breakdown[k] = current_breakdown.get(k, 0) + v
            tracking.usage_breakdown = current_breakdown
            
        session.add(tracking)
        session.commit()

    @staticmethod
    def process_usage(
        session: Session,
        org_id: uuid.UUID,
        workspace_id: Optional[uuid.UUID],
        user_id: uuid.UUID,
        amount: Decimal,
        description: str,
        metadata: Optional[dict] = None
    ) -> OrganizationCreditTransaction:
        """
        Process usage deduction:
        1. Check workspace limit (if workspace provided)
        2. Deduct from Organization balance
        3. Track usage in WorkspaceUsageTracking (if workspace provided)
        """
        
        # 1. Check Workspace Limit
        if workspace_id and amount > 0: 
             OrganizationCreditService.check_workspace_limit(session, workspace_id, amount)

        # 2. Process Transaction (Deduct from Org)
        # We pass -amount because process_transaction expects signed amount
        transaction = OrganizationCreditService.process_transaction(
            session, org_id, -amount, "usage", description, workspace_id, user_id
        )
        
        # 3. Track Workspace Usage
        if workspace_id:
            OrganizationCreditService.track_workspace_usage(session, workspace_id, org_id, amount, metadata)
        
        return transaction
    
    @staticmethod
    def log_transaction(
        session: Session,
        org_id: uuid.UUID,
        amount: Decimal,
        transaction_type: str,
        description: str,
        workspace_id: Optional[uuid.UUID] = None,
        performed_by: Optional[uuid.UUID] = None,
        commit: bool = True
    ) -> OrganizationCreditTransaction:
        """
        Record a transaction in the organization historical ledger.
        This table is used by the Transaction History UI.
        """
        logger.info(f"Logging org transaction: Org={org_id}, Amt={amount}, Type={transaction_type}, Desc={description}")
        # Get current balance for the record
        wallet = WalletService.get_or_create_wallet(session, org_id, WalletOwnerType.ORGANIZATION)
        current_balance = WalletService.get_balance(session, wallet.id)
        
        org_tx = OrganizationCreditTransaction(
            organization_id=org_id,
            amount=amount,
            balance_after=current_balance,
            transaction_type=transaction_type,
            description=description,
            workspace_id=workspace_id,
            performed_by=performed_by
        )
        session.add(org_tx)
        
        if commit:
            session.commit()
            session.refresh(org_tx)
            logger.info(f"Org transaction committed: ID={org_tx.id}")
            
        return org_tx

    @staticmethod
    def share_credits(
        session: Session,
        org_id: uuid.UUID,
        member_id: uuid.UUID,
        amount: Decimal,
        admin_id: uuid.UUID,
        description: Optional[str] = None,
        workspace_id: Optional[uuid.UUID] = None,
        commit: bool = True
    ) -> OrganizationCreditTransaction:
        """
        Transfer credits from Org Treasury to Member and log in organization history.
        """
        logger.info(f"Sharing credits from Org {org_id} to Member {member_id}: Amt={amount}")
        # 1. Perform atomic wallet transfer
        WalletService.share_credits(
            session=session,
            org_id=org_id,
            member_id=member_id,
            amount=amount,
            admin_id=admin_id,
            description=description,
            commit=False # We handle commit here
        )
        
        # Fetch recipient user for logging
        recipient_user = session.get(User, member_id)
        recipient_info = recipient_user.email if recipient_user else str(member_id)
        
        # 2. Log in Organization History (debit)
        hist_entry = OrganizationCreditService.log_transaction(
            session=session,
            org_id=org_id,
            amount=-amount,
            transaction_type="allocation",
            description=description or f"Distributed {amount} credits to {recipient_info}",
            workspace_id=workspace_id,
            performed_by=admin_id,
            commit=commit
        )
        
        return hist_entry

    @staticmethod
    def process_transaction(
        session: Session,
        org_id: uuid.UUID,
        amount: Decimal,
        transaction_type: str,
        description: str,
        workspace_id: Optional[uuid.UUID] = None,
        user_id: Optional[uuid.UUID] = None
    ) -> Any:
        logger.info(f"Applying transaction to Org {org_id}: {amount} credits (Type: {transaction_type})")
        logger.info(f"Processing org transaction: Org={org_id}, Amt={amount}, Type={transaction_type}")
        # Use WalletService for the ledger
        wallet = WalletService.get_or_create_wallet(session, org_id, WalletOwnerType.ORGANIZATION)
        
        # Map old types to new ledger types
        tx_type = WalletTransactionType.TOP_UP if transaction_type in ["topup", "manual_allocation"] else \
                  WalletTransactionType.USAGE if transaction_type == "usage" else \
                  WalletTransactionType.CREDIT_SHARE if transaction_type == "allocation" else \
                  WalletTransactionType.REFUND if transaction_type == "refund" else \
                  WalletTransactionType.ADJUSTMENT
                  
        credit = amount if amount > 0 else Decimal("0.0000")
        debit = abs(amount) if amount < 0 else Decimal("0.0000")
        
        WalletService.add_transaction(
            session=session,
            wallet_id=wallet.id,
            transaction_type=tx_type,
            amount=amount,
            credit=credit,
            debit=debit,
            description=description,
            created_by=user_id,
            source="organization_service"
        )
        
        # Use the unified logging helper
        return OrganizationCreditService.log_transaction(
            session=session,
            org_id=org_id,
            amount=amount,
            transaction_type=transaction_type,
            description=description,
            workspace_id=workspace_id,
            performed_by=user_id,
            commit=True
        )
