from fastapi import APIRouter, Depends
from pydantic.networks import EmailStr

from app.api.deps import get_current_active_superuser
from app.models import Message
from app.utils import send_test_email

router = APIRouter(prefix="/utils", tags=["utils"])


@router.post(
    "/test-email/",
    dependencies=[Depends(get_current_active_superuser)],
    status_code=201,
)
def test_email(email_to: EmailStr) -> Message:
    """
    Test emails.
    """
    send_test_email(email_to=email_to)
    return Message(message="Test email sent.")


@router.get("/health-check")
async def health_check() -> bool:
    return True


@router.get("/sentry-debug")
async def trigger_error():
    # This route is only for verifying Sentry integration
    division_by_zero = 1 / 0
    return {"message": "Should have failed"}
