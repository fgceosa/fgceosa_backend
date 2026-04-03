"""
Monnify payment provider (DEPRECATED).

This provider is deprecated in favor of Flutterwave.
Kept for backward compatibility and potential future reactivation.
"""

from app.payments.providers.monnify.provider import MonnifyProvider

__all__ = ['MonnifyProvider']
