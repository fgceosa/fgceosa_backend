from uuid import UUID
from datetime import datetime
from decimal import Decimal
from sqlmodel import SQLModel
from typing import List, Optional, Dict
from pydantic import field_serializer

class OrganizationCreditBalance(SQLModel):
    balance: Decimal
    currency: str = "QRB"
    monthly_usage: Decimal
    remaining_credits: Decimal
    
    @field_serializer('balance', 'monthly_usage', 'remaining_credits')
    def serialize_decimal(self, value: Decimal) -> float:
        """Serialize Decimal to float with 2 decimal places"""
        return round(float(value), 2)

class OrganizationCreditTransactionPublic(SQLModel):
    id: UUID
    organization_id: UUID
    amount: Decimal
    balance_after: Decimal
    transaction_type: str
    description: Optional[str] = None
    workspace_id: Optional[UUID] = None
    performed_by: Optional[UUID] = None
    created_at: datetime
    workspace_name: Optional[str] = None
    user_name: Optional[str] = None
    
    @field_serializer('amount', 'balance_after')
    def serialize_decimal(self, value: Decimal) -> float:
        """Serialize Decimal to float with 2 decimal places"""
        return round(float(value), 2)

class OrganizationCreditTransactionsList(SQLModel):
    transactions: List[OrganizationCreditTransactionPublic]
    total: int
    page: int
    page_size: int

class WorkspaceUsageBreakdown(SQLModel):
    workspace_id: Optional[UUID] = None
    workspace_name: str
    total_usage: Decimal
    monthly_limit: Decimal
    usage_percentage: float
    breakdown: Dict[str, Decimal]
    
    @field_serializer('total_usage', 'monthly_limit')
    def serialize_decimal(self, value: Decimal) -> float:
        """Serialize Decimal to float with 2 decimal places"""
        return round(float(value), 2)

class DailyUsage(SQLModel):
    date: str
    tokens: int
    requests: int

class OrganizationUsageSummary(SQLModel):
    total_usage: Decimal
    total_api_calls: int = 0
    workspaces_usage: List[WorkspaceUsageBreakdown]
    period_start: datetime
    period_end: datetime
    avg_latency: float = 0.0
    success_rate: float = 100.0
    daily_usage: List[DailyUsage] = []
    
    @field_serializer('total_usage')
    def serialize_decimal(self, value: Decimal) -> float:
        """Serialize Decimal to float with 2 decimal places"""
        return round(float(value), 2)

class WorkspaceLimitUpdate(SQLModel):
    monthly_limit: Decimal
    
    @field_serializer('monthly_limit')
    def serialize_decimal(self, value: Decimal) -> float:
        """Serialize Decimal to float with 2 decimal places"""
        return round(float(value), 2)

class MemberCreditAllocation(SQLModel):
    user_id: UUID
    amount: Decimal
    message: Optional[str] = None
