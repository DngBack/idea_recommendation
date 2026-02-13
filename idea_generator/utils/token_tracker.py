"""
Lightweight token-usage tracker.
Accumulates prompt / completion token counts and calculates estimated cost.
"""

import logging
from collections import defaultdict
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Pricing per token (USD) – add models as needed.
MODEL_PRICES: Dict[str, Dict[str, float]] = {
    "gpt-4o-2024-11-20": {"prompt": 2.5e-6, "cached": 1.25e-6, "completion": 10e-6},
    "gpt-4o-2024-08-06": {"prompt": 2.5e-6, "cached": 1.25e-6, "completion": 10e-6},
    "gpt-4o-2024-05-13": {"prompt": 5.0e-6, "completion": 15e-6},
    "gpt-4o-mini-2024-07-18": {"prompt": 0.15e-6, "cached": 0.075e-6, "completion": 0.6e-6},
    "o1-2024-12-17": {"prompt": 15e-6, "cached": 7.5e-6, "completion": 60e-6},
    "o1-preview-2024-09-12": {"prompt": 15e-6, "cached": 7.5e-6, "completion": 60e-6},
    "o3-mini-2025-01-31": {"prompt": 1.1e-6, "cached": 0.55e-6, "completion": 4.4e-6},
}


class TokenTracker:
    """Accumulate token counts by model."""

    def __init__(self) -> None:
        self.counts: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"prompt": 0, "completion": 0, "reasoning": 0, "cached": 0}
        )

    def add(
        self,
        model: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        reasoning_tokens: int = 0,
        cached_tokens: int = 0,
    ) -> None:
        self.counts[model]["prompt"] += prompt_tokens
        self.counts[model]["completion"] += completion_tokens
        self.counts[model]["reasoning"] += reasoning_tokens
        self.counts[model]["cached"] += cached_tokens

    def cost(self, model: str) -> float:
        """Estimate cost in USD for a given model."""
        prices = MODEL_PRICES.get(model)
        if not prices:
            return 0.0
        t = self.counts[model]
        prompt_cost = (t["prompt"] - t["cached"]) * prices.get("prompt", 0)
        cached_cost = t["cached"] * prices.get("cached", prices.get("prompt", 0))
        completion_cost = t["completion"] * prices.get("completion", 0)
        return prompt_cost + cached_cost + completion_cost

    def summary(self) -> Dict[str, Dict]:
        """Return a summary dict with token counts and estimated cost per model."""
        out = {}
        for model, tokens in self.counts.items():
            out[model] = {
                "tokens": dict(tokens),
                "cost_usd": round(self.cost(model), 4),
            }
        return out

    def print_summary(self) -> None:
        for model, info in self.summary().items():
            t = info["tokens"]
            logger.info(
                "Model %-40s  prompt=%d  completion=%d  cached=%d  cost=$%.4f",
                model,
                t["prompt"],
                t["completion"],
                t["cached"],
                info["cost_usd"],
            )


# Global singleton
token_tracker = TokenTracker()
