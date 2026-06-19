from collections.abc import Callable
from time import sleep
from typing import TypeVar

from config import NormalizationConfig
from linkedin_tool.schema import Result, ScrapeResult

T = TypeVar("T")


def run_with_groq_key_rotation(
    phase: str,
    call: Callable[[str], Result[T]],
) -> Result[T]:
    errors: list[str] = []
    api_keys = NormalizationConfig.GROQ_API_KEYS.value

    for index, api_key in enumerate(api_keys):
        try:
            result = call(api_key)
        except Exception as e:
            errors.append(f"key[{index}]: {e}")
        else:
            if result.result == ScrapeResult.SUCCESSFUL:
                return result

            errors.append(f"key[{index}]: {result.error or result.result.value}")

        if index < len(api_keys) - 1:
            sleep(NormalizationConfig.LLM_INTERVAL.value)

    return Result(
        result=ScrapeResult.FAILED,
        content=None,
        error=f"{phase} failed for all Groq API keys: {'; '.join(errors)}",
    )