"""
Payment Factory - Provider Switching Mechanism.

This factory enables plug-and-play switching between payment providers.
Simply change the PAYMENT_PROVIDER environment variable to switch providers.
"""

from app.core.config import settings
from app.payments.provider_protocol import PaymentProviderProtocol


class PaymentFactory:
    """
    Factory class for creating payment provider instances.

    Enables easy switching between payment providers by reading from
    environment configuration.

    Usage:
        provider = PaymentFactory.get_provider()
        result = await provider.generate_bank_transfer_details(...)
    """

    _provider_cache: PaymentProviderProtocol = None

    @staticmethod
    def get_provider() -> PaymentProviderProtocol:
        """
        Get the active payment provider based on configuration.

        Reads the PAYMENT_PROVIDER environment variable and returns
        the appropriate provider instance. Uses singleton pattern to
        avoid recreating provider instances.

        Returns:
            Payment provider instance implementing PaymentProviderProtocol

        Raises:
            ValueError: If the configured provider is not supported

        Example:
            # In .env file
            PAYMENT_PROVIDER=flutterwave

            # In code
            provider = PaymentFactory.get_provider()
            # Returns FlutterwaveProvider instance
        """
        # Return cached provider if available
        if PaymentFactory._provider_cache is not None:
            return PaymentFactory._provider_cache

        provider_name = settings.PAYMENT_PROVIDER.lower()

        if provider_name == "flutterwave":
            from app.payments.providers.flutterwave import FlutterwaveProvider
            PaymentFactory._provider_cache = FlutterwaveProvider()

        elif provider_name == "monnify":
            from app.payments.providers.monnify import MonnifyProvider
            PaymentFactory._provider_cache = MonnifyProvider()

        # Add more providers here as needed
        # elif provider_name == "paystack":
        #     from app.payments.providers.paystack import PaystackProvider
        #     PaymentFactory._provider_cache = PaystackProvider()
        #
        # elif provider_name == "stripe":
        #     from app.payments.providers.stripe import StripeProvider
        #     PaymentFactory._provider_cache = StripeProvider()

        else:
            raise ValueError(
                f"Unsupported payment provider: {provider_name}. "
                f"Supported providers: flutterwave, monnify"
            )

        return PaymentFactory._provider_cache

    @staticmethod
    def reset_cache():
        """
        Reset the provider cache.

        Useful for testing or when you need to force provider reload.
        """
        PaymentFactory._provider_cache = None

    @staticmethod
    def get_provider_name() -> str:
        """
        Get the name of the currently active provider.

        Returns:
            Provider name string (e.g., 'flutterwave', 'monnify')
        """
        return settings.PAYMENT_PROVIDER.lower()

    @staticmethod
    def is_provider_available(provider_name: str) -> bool:
        """
        Check if a specific provider is available.

        Args:
            provider_name: Name of the provider to check

        Returns:
            True if provider is available, False otherwise
        """
        supported_providers = ["flutterwave", "monnify"]
        return provider_name.lower() in supported_providers
