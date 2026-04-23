"""
Paystack Exceptions.
"""

class PaystackException(Exception):
    """Base exception for Paystack provider."""
    pass

class PaystackAuthenticationException(PaystackException):
    """Raised when authentication with Paystack fails."""
    pass

class PaystackPaymentException(PaystackException):
    """Raised when a payment operation fails."""
    pass
