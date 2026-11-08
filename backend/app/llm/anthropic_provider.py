import os
from decimal import Decimal
import anthropic
from .base import BaseLLMProvider, LLMResponse

MODEL = "claude-sonnet-4-5"
# Pricing per million tokens (USD)
INPUT_COST_PER_M = Decimal("3.00")
OUTPUT_COST_PER_M = Decimal("15.00")


class AnthropicProvider(BaseLLMProvider):
    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    async def complete(self, system: str, user: str, temperature: float = 0) -> LLMResponse:
        msg = await self.client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        content = msg.content[0].text
        in_tok = msg.usage.input_tokens
        out_tok = msg.usage.output_tokens
        cost = (
            Decimal(in_tok) / Decimal("1000000") * INPUT_COST_PER_M
            + Decimal(out_tok) / Decimal("1000000") * OUTPUT_COST_PER_M
        ).quantize(Decimal("0.000001"))
        return LLMResponse(
            content=content,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=str(cost),
        )


def get_provider() -> BaseLLMProvider:
    provider = os.getenv("LLM_PROVIDER", "anthropic").lower()
    if provider == "anthropic":
        return AnthropicProvider()
    raise ValueError(f"Unknown LLM_PROVIDER: {provider}")
