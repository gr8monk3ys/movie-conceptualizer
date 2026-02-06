"""Base agent class with common LLM interaction patterns.

This module provides the foundation for all AI agents in the movie conceptualizer
pipeline, including common functionality for structured output generation with
Claude via LangChain.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any, TypeVar

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

# Type variable for structured output
T = TypeVar("T", bound=BaseModel)


class APIKeyNotFoundError(Exception):
    """Raised when no API key is available for LLM initialization."""

    def __init__(self, provider: str = "Anthropic"):
        self.provider = provider
        env_var = "OPENAI_API_KEY" if provider.lower() == "openai" else "ANTHROPIC_API_KEY"
        super().__init__(
            f"No {provider} API key found. Please set the {env_var} "
            "environment variable or pass api_key to the agent constructor."
        )


class BaseAgent(ABC):
    """Base class for all agents in the movie conceptualizer pipeline.

    This class provides common functionality for:
    - LLM initialization and configuration
    - Structured output generation with Pydantic models
    - Error handling and retry logic
    - Consistent prompting patterns

    The LLM is initialized lazily on first access, allowing agent creation
    without immediately requiring an API key.
    """

    def __init__(
        self,
        model_name: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        api_key: str | None = None,
        provider: str | None = None,
    ):
        """Initialize the base agent.

        Args:
            model_name: The model to use (default depends on provider)
            temperature: Sampling temperature (0.0 to 1.0)
            max_tokens: Maximum tokens in response
            api_key: Provider API key (defaults to env)
            provider: LLM provider name ("anthropic" or "openai")

        Note:
            The LLM is initialized lazily on first access to the `llm` property.
            This allows creating agent instances without immediately requiring
            an API key (useful for testing, configuration, etc.).
        """
        env_provider = os.environ.get("MOVIECON_LLM_PROVIDER")
        self.provider = (provider or env_provider or "anthropic").lower()
        self.model_name = model_name or self._default_model_name()
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._api_key = api_key
        self._llm: BaseChatModel | None = None

    def _default_model_name(self) -> str:
        """Select a default model name based on provider and env overrides."""
        env_model = os.environ.get("MOVIECON_LLM_MODEL")
        if env_model:
            return env_model
        if self.provider == "openai":
            return os.environ.get("MOVIECON_OPENAI_MODEL", "gpt-4o-mini")
        return os.environ.get("MOVIECON_ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

    def _get_api_key(self) -> str:
        """Get the API key, checking environment if not explicitly set."""
        if self._api_key:
            return self._api_key
        if self.provider == "openai":
            env_key = os.environ.get("OPENAI_API_KEY")
        else:
            env_key = os.environ.get("ANTHROPIC_API_KEY")
        if env_key:
            return env_key
        raise APIKeyNotFoundError("OpenAI" if self.provider == "openai" else "Anthropic")

    def _init_llm(self) -> BaseChatModel:
        """Initialize the LLM instance.

        Returns:
            Configured ChatAnthropic instance

        Raises:
            APIKeyNotFoundError: If no API key is available
        """
        api_key = self._get_api_key()
        if self.provider == "openai":
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                model=self.model_name,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                api_key=api_key,
            )
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=self.model_name,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            api_key=api_key,
        )

    @property
    def llm(self) -> BaseChatModel:
        """Get the underlying LLM instance (lazy initialization).

        Returns:
            The configured LLM instance

        Raises:
            APIKeyNotFoundError: If no API key is available
        """
        if self._llm is None:
            self._llm = self._init_llm()
        return self._llm

    def is_configured(self) -> bool:
        """Check if the agent has a valid API key configured.

        Returns:
            True if an API key is available (either explicit or from env)
        """
        try:
            self._get_api_key()
            return True
        except APIKeyNotFoundError:
            return False

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Return the system prompt for this agent.

        Subclasses must implement this to provide their specialized
        system prompt that defines the agent's role and behavior.
        """
        pass

    @property
    @abstractmethod
    def agent_name(self) -> str:
        """Return the name of this agent for logging and identification."""
        pass

    def _create_prompt_template(
        self,
        user_template: str,
        input_variables: list[str],
    ) -> ChatPromptTemplate:
        """Create a chat prompt template with system and user messages.

        Args:
            user_template: The user message template with placeholders
            input_variables: List of variable names used in the template

        Returns:
            A configured ChatPromptTemplate
        """
        return ChatPromptTemplate.from_messages([
            ("system", self.system_prompt),
            ("human", user_template),
        ])

    def generate_structured_output(
        self,
        output_schema: type[T],
        user_prompt: str,
        **kwargs: Any,
    ) -> T:
        """Generate a structured output using the specified Pydantic model.

        This method uses LangChain's with_structured_output to ensure the
        LLM response conforms to the specified Pydantic schema.

        Args:
            output_schema: The Pydantic model class to use for output
            user_prompt: The user message/prompt to send
            **kwargs: Additional variables to format into the prompt

        Returns:
            An instance of the output_schema Pydantic model

        Raises:
            ValueError: If the LLM fails to generate valid structured output
        """
        # Create a structured LLM that outputs the specified schema
        structured_llm = self.llm.with_structured_output(output_schema)

        # Build messages
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=user_prompt.format(**kwargs) if kwargs else user_prompt),
        ]

        # Generate the response
        result = structured_llm.invoke(messages)

        if result is None:
            raise ValueError(
                f"{self.agent_name}: Failed to generate structured output. "
                "The LLM response could not be parsed into the expected schema."
            )

        return result

    async def agenerate_structured_output(
        self,
        output_schema: type[T],
        user_prompt: str,
        **kwargs: Any,
    ) -> T:
        """Async version of generate_structured_output.

        Args:
            output_schema: The Pydantic model class to use for output
            user_prompt: The user message/prompt to send
            **kwargs: Additional variables to format into the prompt

        Returns:
            An instance of the output_schema Pydantic model

        Raises:
            ValueError: If the LLM fails to generate valid structured output
        """
        # Create a structured LLM that outputs the specified schema
        structured_llm = self.llm.with_structured_output(output_schema)

        # Build messages
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=user_prompt.format(**kwargs) if kwargs else user_prompt),
        ]

        # Generate the response asynchronously
        result = await structured_llm.ainvoke(messages)

        if result is None:
            raise ValueError(
                f"{self.agent_name}: Failed to generate structured output. "
                "The LLM response could not be parsed into the expected schema."
            )

        return result

    def generate_text(self, user_prompt: str, **kwargs: Any) -> str:
        """Generate a plain text response from the LLM.

        Args:
            user_prompt: The user message/prompt to send
            **kwargs: Additional variables to format into the prompt

        Returns:
            The LLM's text response
        """
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=user_prompt.format(**kwargs) if kwargs else user_prompt),
        ]

        response = self.llm.invoke(messages)
        return response.content

    async def agenerate_text(self, user_prompt: str, **kwargs: Any) -> str:
        """Async version of generate_text.

        Args:
            user_prompt: The user message/prompt to send
            **kwargs: Additional variables to format into the prompt

        Returns:
            The LLM's text response
        """
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=user_prompt.format(**kwargs) if kwargs else user_prompt),
        ]

        response = await self.llm.ainvoke(messages)
        return response.content

    @abstractmethod
    def process(self, *args: Any, **kwargs: Any) -> Any:
        """Process input and return output.

        Subclasses must implement this method to define their specific
        processing logic.
        """
        pass

    async def aprocess(self, *args: Any, **kwargs: Any) -> Any:
        """Async version of process.

        Subclasses can override this for async processing.
        Default implementation calls the sync version.
        """
        return self.process(*args, **kwargs)

    def __repr__(self) -> str:
        """Return string representation of the agent."""
        return (
            f"{self.__class__.__name__}("
            f"model={self.model_name}, "
            f"temperature={self.temperature})"
        )
