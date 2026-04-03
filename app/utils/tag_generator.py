"""
Qorebit Tag Number Generator

Generates unique tag numbers for users (e.g., @qor123456)
Similar to Cash App $cashtags or Venmo @username
"""

import random
import string
import logging
from sqlmodel import Session, select
from app.models import User

logger = logging.getLogger(__name__)


def generate_tag_number(session: Session, prefix: str = "qor", length: int = 6, max_attempts: int = 10) -> str:
    """
    Generate a unique tag number for a user.

    Args:
        session: Database session
        prefix: Tag prefix (default: "qor")
        length: Length of random part (default: 6)
        max_attempts: Maximum attempts to find unique tag (default: 10)

    Returns:
        Unique tag number (e.g., "qor123abc")

    Raises:
        RuntimeError: If unable to generate unique tag after max_attempts

    Examples:
        >>> generate_tag_number(session)
        'qor7k2m9p'
        >>> generate_tag_number(session, prefix="qbt", length=8)
        'qbt4f8h2k9x1'
    """

    # Use combination of numbers and lowercase letters for readability
    # Exclude confusing characters: 0, O, o, 1, l, I
    characters = '23456789abcdefghjkmnpqrstuvwxyz'

    for attempt in range(max_attempts):
        # Generate random part
        random_part = ''.join(random.choices(characters, k=length))
        tag_number = f"{prefix}{random_part}"

        # Check if tag already exists
        statement = select(User).where(User.tag_number == tag_number)
        existing_user = session.exec(statement).first()

        if not existing_user:
            logger.info(f"Generated unique tag number: {tag_number}")
            return tag_number

        logger.debug(f"Tag collision on attempt {attempt + 1}: {tag_number}")

    # If we get here, we couldn't generate a unique tag
    raise RuntimeError(
        f"Failed to generate unique tag number after {max_attempts} attempts. "
        f"Consider increasing length or max_attempts."
    )


def assign_tag_number(session: Session, user: User, commit: bool = True) -> str:
    """
    Assign a unique tag number to a user if they don't have one.

    Args:
        session: Database session
        user: User object to assign tag to
        commit: Whether to commit the session (default: True)

    Returns:
        The assigned tag number

    Raises:
        RuntimeError: If unable to generate unique tag
    """

    # Check if user already has a tag
    if user.tag_number:
        logger.info(f"User {user.id} already has tag number: {user.tag_number}")
        return user.tag_number

    # Generate and assign tag
    tag_number = generate_tag_number(session)
    user.tag_number = tag_number

    session.add(user)

    if commit:
        session.commit()
        session.refresh(user)

    logger.info(f"Assigned tag number {tag_number} to user {user.id} ({user.email})")
    return tag_number


def format_tag_display(tag_number: str | None, include_at: bool = True) -> str:
    """
    Format tag number for display.

    Args:
        tag_number: The tag number (with or without @)
        include_at: Whether to include @ prefix (default: True)

    Returns:
        Formatted tag number for display

    Examples:
        >>> format_tag_display("qor123abc")
        '@qor123abc'
        >>> format_tag_display("@qor123abc")
        '@qor123abc'
        >>> format_tag_display("qor123abc", include_at=False)
        'qor123abc'
    """

    if not tag_number:
        return ""

    # Remove @ if present
    clean_tag = tag_number.lstrip('@')

    # Add @ if requested
    if include_at:
        return f"@{clean_tag}"

    return clean_tag


def normalize_tag_number(tag_input: str) -> str:
    """
    Normalize tag number input (remove @ prefix, lowercase).

    Args:
        tag_input: User input for tag number

    Returns:
        Normalized tag number

    Examples:
        >>> normalize_tag_number("@QOR123ABC")
        'qor123abc'
        >>> normalize_tag_number("qor123abc")
        'qor123abc'
    """

    # Remove @ prefix and convert to lowercase
    return tag_input.lstrip('@').lower().strip()


def is_valid_tag_format(tag_number: str) -> bool:
    """
    Validate tag number format.

    Args:
        tag_number: Tag number to validate

    Returns:
        True if valid format, False otherwise

    Examples:
        >>> is_valid_tag_format("qor123abc")
        True
        >>> is_valid_tag_format("qor")
        False
        >>> is_valid_tag_format("abc123")
        False
    """

    # Must start with 'qor' prefix
    if not tag_number.startswith('qor'):
        return False

    # Must have additional characters after prefix
    if len(tag_number) <= 3:
        return False

    # Check if contains only alphanumeric characters
    if not tag_number.isalnum():
        return False

    return True
