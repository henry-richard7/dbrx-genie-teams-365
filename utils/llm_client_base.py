"""
Base LLM client module.

Provides the BaseLLMClient class for interacting with Databricks or OpenAI models,
managing caching, TTL, and credential fallback.
"""
import json
import logging
import time
from os import environ
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

class BaseLLMClient:
    """Base class for LLM clients interacting with Databricks models.
    
    Handles Databricks WorkspaceClient authentication fallback, ChatOpenAI model
    instantiation, token TTL caching, and JSON extraction from LLM outputs.
    """

    # Refresh cached models after 55 min (Databricks OAuth tokens expire at 60 min)
    _TOKEN_TTL_SECONDS = 55 * 60

    def __init__(self):
        """Initializes the BaseLLMClient and its internal caches."""
        self._models = {}
        self._model_created_at = {}  # cache_key -> float (epoch seconds)
        self._workspace_clients = {}

    def _get_or_create_model(
        self, client_id: str | None = None, client_secret: str | None = None, temperature: float = 0.0
    ) -> ChatOpenAI | None:
        """Returns a cached (or newly created) ChatOpenAI instance for the given scope.
        
        Evicts and recreates the model if it has been cached for longer than
        55 minutes to avoid using expired OAuth tokens.
        """
        llm_endpoint = environ.get(
            "OPENAI_MODEL_NAME", "databricks-qwen3-next-80b-a3b-instruct"
        )
        cache_key = client_id or "default"

        # Evict stale model so a fresh token is fetched
        if cache_key in self._models:
            age = time.time() - self._model_created_at.get(cache_key, 0)
            if age < self._TOKEN_TTL_SECONDS:
                return self._models[cache_key]
            logger.debug(
                f"{self.__class__.__name__}: model for scope '{cache_key}' "
                f"expired after {age:.0f}s, refreshing."
            )
            del self._models[cache_key]
            del self._model_created_at[cache_key]

        kwargs: dict = {
            "model": llm_endpoint,
            "temperature": temperature,
        }

        base_url = environ.get("OPENAI_BASE_URL")
        if base_url:
            kwargs["base_url"] = base_url

        kwargs["api_key"] = environ.get("OPENAI_API_KEY")

        if not kwargs["api_key"] or kwargs["api_key"] == "not-provided":
            logger.debug(
                f"{self.__class__.__name__}: no OPENAI_API_KEY, "
                "attempting Databricks WorkspaceClient token."
            )
            from databricks.sdk import WorkspaceClient

            host = environ.get("DATABRICKS_HOST")
            try:
                if cache_key not in self._workspace_clients:
                    if client_id and client_secret:
                        self._workspace_clients[cache_key] = WorkspaceClient(
                            host=host,
                            client_id=client_id,
                            client_secret=client_secret,
                        )
                    else:
                        self._workspace_clients[cache_key] = WorkspaceClient(host=host)

                w = self._workspace_clients[cache_key]
                creds = w.config.authenticate()
                if creds and isinstance(creds, dict) and "Authorization" in creds:
                    kwargs["api_key"] = creds["Authorization"].replace("Bearer ", "")
                elif w.config.token:
                    kwargs["api_key"] = w.config.token

                if "base_url" not in kwargs and host:
                    kwargs["base_url"] = f"{host.rstrip('/')}/serving-endpoints"
            except Exception as exc:
                logger.error(
                    f"{self.__class__.__name__}: failed to obtain Databricks token: {exc}"
                )

        if not kwargs.get("api_key"):
            kwargs["api_key"] = "not-provided"

        try:
            self._models[cache_key] = ChatOpenAI(**kwargs)
            self._model_created_at[cache_key] = time.time()
            return self._models[cache_key]
        except Exception as exc:
            logger.error(
                f"{self.__class__.__name__}: failed to create ChatOpenAI model: {exc}"
            )
            return None

    def _parse_json_response(self, response) -> str:
        """Extracts JSON content from an LLM response, stripping markdown formatting."""
        raw = response.content if hasattr(response, "content") else str(response)
        if isinstance(raw, list):
            text_parts = []
            for item in raw:
                if isinstance(item, dict) and "text" in item:
                    text_parts.append(item["text"])
                elif isinstance(item, str):
                    text_parts.append(item)
            raw = "".join(text_parts) if text_parts else str(raw)
        elif not isinstance(raw, str):
            raw = str(raw)

        raw = raw.strip()

        import re
        match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw, re.DOTALL)
        if match:
            raw = match.group(1)
        else:
            start = raw.find('{')
            end = raw.rfind('}')
            if start != -1 and end != -1:
                raw = raw[start:end+1]
        return raw.strip()
