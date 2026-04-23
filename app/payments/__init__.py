"""
Payment providers package for multi-provider payment integration.

This package implements a modular payment architecture that allows easy switching
between payment providers (Flutterwave, Monnify, Paystack, Stripe, etc.)
"""

from app.payments.provider_protocol import PaymentProviderProtocol
from app.payments.payment_factory import PaymentFactory

__all__ = [
    'PaymentProviderProtocol',
    'PaymentFactory',
]
