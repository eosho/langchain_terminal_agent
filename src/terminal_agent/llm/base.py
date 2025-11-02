from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Type, Literal


PROVIDER_TYPE = Literal["openai", "azure_openai"]


class BaseProvider(ABC):
    """Abstract provider interface.

    Each provider implements `create_client()` to return a fully initialized LLM.
    """

    @abstractmethod
    def create_client(self, **kwargs: Any) -> Any:
        """Return a fully initialized LLM client."""
        pass


class LLMFactory:
    """Central registry & factory for all supported providers. Provides a unified entry point
    to construct an LLM client dynamically based on a provider type.
    """

    _providers: Dict[str, Type[BaseProvider]] = {}

    @classmethod
    def register_provider(cls, name: str, provider_cls: Type[BaseProvider]) -> None:
        """Register a provider implementation.

        Args:
            name: The LLM provider type (e.g., "openai", "azure").
            provider_cls: The provider class implementing BaseProvider.

        Raises:
            ValueError: If the provider name is already registered.
        """
        cls._providers[name.lower()] = provider_cls
        logging.info(f"Registered LLM provider: {name}")

    @classmethod
    def get_provider(cls, name: PROVIDER_TYPE) -> BaseProvider:
        """Return an instantiated provider.

        Args:
            name: The LLM provider type (e.g., "openai", "azure").

        Raises:
            ValueError: If the provider is not registered.
        """
        provider_cls = cls._providers.get(name.lower())
        if not provider_cls:
            raise ValueError(f"Provider not registered: {name}")
        return provider_cls()

    @classmethod
    def create_llm(cls, provider: PROVIDER_TYPE, **kwargs: Any) -> Any:
        """
        Create an LLM client for the requested provider.

        Args:
            provider: The LLM provider type (e.g., "openai", "azure").
            **kwargs: Provider-specific parameters for client initialization.

        Example:
            LLMFactory.create_llm(
                provider=\"azure\",
                api_key=\"...\", azure_endpoint=\"...\", azure_deployment=\"...\", api_version=\"...\"
            )

        Returns:
            An initialized LLM client instance.
        """
        provider_instance = cls.get_provider(provider)
        client = provider_instance.create_client(**kwargs)
        logging.info(f"Created {provider.capitalize()} LLM client successfully.")
        return client


def get_llm(provider: PROVIDER_TYPE, **kwargs: Any):
    """Shortcut to create an LLM client.

    Args:
        provider: The LLM provider type (e.g., "openai", "azure").
        **kwargs: Provider-specific parameters for client initialization.

    Returns:
        An initialized LLM client instance.
    """
    return LLMFactory.create_llm(provider, **kwargs)
