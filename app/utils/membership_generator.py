"""
FGCEOSA Membership ID Generator
Generates unique membership IDs for alumni (e.g., FGC-OSA-2024-ABC12)
"""

import random
import string
import logging
from datetime import datetime, timezone
from sqlmodel import Session, select
from app.models import User

logger = logging.getLogger(__name__)


def generate_membership_id(session: Session, graduation_year: str | None = None, length: int = 5, max_attempts: int = 10) -> str:
    """
    Generate a unique membership ID for a user.
    Format: OSA-[GRAD_YEAR]-[RANDOM]
    """
    
    # Use current year short code if graduation year is missing
    year_part = graduation_year if graduation_year and len(graduation_year) == 4 else str(datetime.now().year)
    
    # Use combination of numbers and uppercase letters for readability
    characters = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ'

    for attempt in range(max_attempts):
        # Generate random part
        random_part = ''.join(random.choices(characters, k=length))
        membership_id = f"OSA-{year_part}-{random_part}"

        # Check if membership_id already exists
        statement = select(User).where(User.membership_id == membership_id)
        existing_user = session.exec(statement).first()

        if not existing_user:
            logger.info(f"Generated unique membership ID: {membership_id}")
            return membership_id

        logger.debug(f"Membership ID collision on attempt {attempt + 1}: {membership_id}")

    # If we get here, we couldn't generate a unique ID
    raise RuntimeError(
        f"Failed to generate unique membership ID after {max_attempts} attempts."
    )


def assign_membership_id(session: Session, user: User, commit: bool = True) -> str:
    """
    Assign a unique membership ID to a user if they don't have one.
    """

    # Check if user already has an ID
    if user.membership_id:
        logger.info(f"User {user.id} already has membership ID: {user.membership_id}")
        return user.membership_id

    # Generate and assign ID
    membership_id = generate_membership_id(session, graduation_year=user.graduation_year)
    user.membership_id = membership_id

    session.add(user)

    if commit:
        session.commit()
        session.refresh(user)

    logger.info(f"Assigned membership ID {membership_id} to user {user.id} ({user.email})")
    return membership_id
