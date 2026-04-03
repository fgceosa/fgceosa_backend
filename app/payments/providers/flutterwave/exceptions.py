"""
Flutterwave-specific exceptions.
"""


class FlutterwaveException(Exception):
    """Base exception for Flutterwave provider errors."""
    pass


class FlutterwaveAuthenticationException(FlutterwaveException):
    """Exception raised for authentication failures."""
    pass


class FlutterwavePaymentException(FlutterwaveException):
    """Exception raised for payment processing failures."""
    pass


class FlutterwaveWebhookException(FlutterwaveException):
    """Exception raised for webhook processing failures."""
    pass
