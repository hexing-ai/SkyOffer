from __future__ import annotations

from dataclasses import dataclass

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    RateLimitError,
)

from backend.app.core.config import Settings


@dataclass(slots=True)
class ModelUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(slots=True)
class ModelResponse:
    content: str
    model_name: str
    usage: ModelUsage


@dataclass(slots=True)
class ModelClientError(Exception):
    kind: str
    retryable: bool


class DeepSeekModelClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        if not self.settings.model_is_configured:
            raise ModelClientError(kind="not_configured", retryable=False)
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self.settings.model_api_key.get_secret_value(),
                base_url=self.settings.model_base_url,
                timeout=self.settings.model_timeout_seconds,
                max_retries=0,
            )
        return self._client

    async def complete(self, messages: list[dict[str, str]]) -> ModelResponse:
        try:
            client = self._get_client()
            response = await client.chat.completions.create(
                model=self.settings.model_name,
                messages=messages,
                temperature=0.1,
                max_tokens=2000,
                response_format={"type": "json_object"},
            )
        except ModelClientError:
            raise
        except AuthenticationError as exc:
            raise ModelClientError(kind="authentication", retryable=False) from exc
        except APITimeoutError as exc:
            raise ModelClientError(kind="timeout", retryable=True) from exc
        except RateLimitError as exc:
            raise ModelClientError(kind="rate_limit", retryable=True) from exc
        except APIConnectionError as exc:
            raise ModelClientError(kind="connection", retryable=True) from exc
        except APIStatusError as exc:
            retryable = exc.status_code >= 500
            raise ModelClientError(kind="upstream", retryable=retryable) from exc
        except Exception as exc:
            raise ModelClientError(kind="unexpected", retryable=False) from exc

        content = response.choices[0].message.content
        if not content:
            raise ModelClientError(kind="empty_output", retryable=True)

        usage = response.usage
        return ModelResponse(
            content=content,
            model_name=response.model or self.settings.model_name,
            usage=ModelUsage(
                input_tokens=getattr(usage, "prompt_tokens", None),
                output_tokens=getattr(usage, "completion_tokens", None),
                total_tokens=getattr(usage, "total_tokens", None),
            ),
        )
