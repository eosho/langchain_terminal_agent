from __future__ import annotations

import logging
from typing import Any
from langchain_openai import ChatOpenAI, AzureChatOpenAI

from .base import BaseProvider, LLMFactory
from terminal_agent.core.config import LLMConfig


class OpenAIProvider(BaseProvider):
    """Provider implementation for OpenAI models.

    This class creates and configures a LangChain `ChatOpenAI` client instance.
    It follows the MCP-Bench provider abstraction pattern, allowing the
    `LLMFactory` to dynamically instantiate the proper model provider.

    Example:
      >>> llm = OpenAIProvider().create_client()
      >>> response = llm.invoke("Summarize key insights from the report.")

    Attributes:
        None
    """

    def create_client(self, **kwargs: Any) -> ChatOpenAI:
        """Instantiate a ChatOpenAI client.

        Args:
            **kwargs: Optional overrides (e.g., temperature, streaming).

        Returns:
            ChatOpenAI: A fully initialized LangChain `ChatOpenAI` instance.

        Raises:
            ValueError: If required parameters (`api_key` or `model`) are missing.
        """
        api_key = LLMConfig.openai_api_key
        model = LLMConfig.model

        if not api_key or not model:
            raise ValueError(
                "Missing required OpenAI configuration: "
                "OPENAI_API_KEY or OPENAI_MODEL not set."
            )

        logging.debug(f"Initializing OpenAI Chat model: {model}")

        return ChatOpenAI(
            api_key=api_key,    # type: ignore
            model=model,
            **kwargs,
        )


class AzureOpenAIProvider(BaseProvider):
    """Provider implementation for Azure-hosted OpenAI models.

    This class creates and configures a LangChain `AzureChatOpenAI` client.
    It enables Azure-specific deployment parameters and integrates seamlessly
    with the MCP-Bench style LLM factory registry.

    Example:
        >>> llm = AzureOpenAIProvider().create_client()
        >>> response = llm.invoke("Generate recommendations for store insights.")

    Attributes:
        None
    """

    def create_client(self, **kwargs: Any) -> AzureChatOpenAI:
        """Instantiate an AzureChatOpenAI client.

        Args:
            **kwargs: Optional runtime overrides (e.g., temperature, max_tokens, streaming).

        Returns:
            AzureChatOpenAI: A fully initialized LangChain `AzureChatOpenAI` instance.

        Raises:
            ValueError: If any required Azure configuration parameters are missing.
        """
        api_key = LLMConfig.azure_api_key
        endpoint = LLMConfig.azure_endpoint
        deployment = LLMConfig.azure_deployment
        api_version = LLMConfig.azure_api_version

        if not all([api_key, endpoint, deployment, api_version]):
            raise ValueError(
                "Missing required Azure OpenAI configuration. Ensure the following "
                "are defined in your environment: "
                "AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, "
                "AZURE_OPENAI_DEPLOYMENT, AZURE_OPENAI_API_VERSION."
            )

        logging.debug(f"Initializing Azure OpenAI deployment: {deployment}")

        return AzureChatOpenAI(
            api_key=api_key,    # type: ignore
            azure_endpoint=endpoint,
            azure_deployment=deployment,
            api_version=api_version,
            **kwargs,
        )


# Register only the provider specified in settings
def _register_configured_provider():
    """Register only the LLM provider that's configured in settings."""
    provider_name = LLMConfig.provider.lower()
    
    if provider_name == "openai":
        LLMFactory.register_provider("openai", OpenAIProvider)
    elif provider_name == "azure_openai":
        LLMFactory.register_provider("azure_openai", AzureOpenAIProvider)
    else:
        logging.warning(f"Unknown LLM provider configured: {provider_name}")


# Register the configured provider on module import
_register_configured_provider()
