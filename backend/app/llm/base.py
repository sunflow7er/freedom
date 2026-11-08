from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class LLMResponse:
    content: str
    input_tokens: int
    output_tokens: int
    cost_usd: Optional[str] = None


class BaseLLMProvider(ABC):
    @abstractmethod
    async def complete(self, system: str, user: str, temperature: float = 0) -> LLMResponse:
        pass
