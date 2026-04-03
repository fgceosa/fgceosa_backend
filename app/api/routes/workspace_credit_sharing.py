"""
Workspace Credit Sharing API Endpoints

Provides endpoints for workspace admins to share credits with team members.
"""

import uuid
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.api.deps import CurrentUser, SessionDep
from app.services.workspace_credit_sharing import (
    CreditShareRequest,
    CreditShareResponse,
    share_credits_bulk,
)

router = APIRouter()


@router.post(
    "/workspaces/{workspace_id}/share-credits",
    response_model=CreditShareResponse,
    status_code=status.HTTP_200_OK,
    summary="Share credits with team members",
    description="""
    Share AI credits from workspace wallet to one or multiple team members.

    **Features:**
    - Single or bulk transfer
    - Identify recipients by email or tag number
    - Specify amount per user or split total equally
    - Atomic transactions (all succeed or none)
    - Optional transfer message

    **Permissions:** Requires workspace admin or owner access

    **Examples:**

    1. Equal split to multiple users:
    ```json
    {
        "recipients": [
            {"email": "user1@example.com"},
            {"tag_number": "@qor123456"}
        ],
        "total_amount": 100.0,
        "message": "Monthly allocation"
    }
    ```

    2. Custom amount per user:
    ```json
    {
        "recipients": [
            {"email": "user1@example.com", "amount": 25.0},
            {"tag_number": "@qor123456", "amount": 75.0}
        ],
        "message": "Performance bonus"
    }
    ```

    3. Fixed amount per user:
    ```json
    {
        "recipients": [
            {"email": "user1@example.com"},
            {"email": "user2@example.com"}
        ],
        "amount_per_user": 50.0,
        "message": "Weekly credit"
    }
    ```
    """,
)
async def share_workspace_credits(
    workspace_id: uuid.UUID,
    request: CreditShareRequest,
    session: SessionDep,
    current_user: CurrentUser,
) -> CreditShareResponse:
    """
    Share credits from workspace to team members.

    Validates:
    - Admin permissions
    - Workspace balance
    - Recipient existence

    Returns success/failure status for each recipient.
    """
    return await share_credits_bulk(
        session=session,
        workspace_id=workspace_id,
        admin_user=current_user,
        request=request,
    )


@router.get(
    "/workspaces/{workspace_id}/share-credits/preview",
    summary="Preview credit share calculation",
    description="Calculate how credits will be distributed without executing the transfer",
)
async def preview_credit_share(
    workspace_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
    total_amount: float | None = None,
    amount_per_user: float | None = None,
    recipient_count: int = 1,
):
    """
    Preview credit distribution calculation.

    Helps admins understand credit allocation before executing.
    """
    from decimal import Decimal
    from app.models import Workspace
    from app.services.workspace_service import check_workspace_access

    workspace = session.get(Workspace, workspace_id)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found"
        )

    check_workspace_access(session=session, workspace=workspace, user=current_user)

    if total_amount:
        per_user = Decimal(str(total_amount)) / recipient_count
        total = Decimal(str(total_amount))
    elif amount_per_user:
        per_user = Decimal(str(amount_per_user))
        total = per_user * recipient_count
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either total_amount or amount_per_user must be provided"
        )

    return {
        "workspace_id": workspace_id,
        "current_balance": workspace.credits_balance,
        "total_to_distribute": float(total),
        "amount_per_user": float(per_user),
        "recipient_count": recipient_count,
        "balance_after": float(workspace.credits_balance - total),
        "sufficient_balance": workspace.credits_balance >= total,
    }
