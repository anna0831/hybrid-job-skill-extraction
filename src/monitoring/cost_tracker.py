"""成本與資源監控追蹤模組 (Cost & Latency Tracker)。

追蹤 LLM 調用次數、Token 消耗量、推論延遲與預估 API 費用，
落實成本安全防線與每千筆職缺成本統計。
"""

import time
import logging
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class CostStats(BaseModel):
    """成本統計資料模型。"""
    total_jobs: int = 0
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    total_latency_ms: float = 0.0
    estimated_cost_usd: float = 0.0

    @property
    def avg_latency_ms(self) -> float:
        return (self.total_latency_ms / self.total_jobs) if self.total_jobs > 0 else 0.0

    @property
    def cost_per_1k_jobs_usd(self) -> float:
        return (self.estimated_cost_usd / self.total_jobs * 1000.0) if self.total_jobs > 0 else 0.0

    @property
    def llm_call_rate(self) -> float:
        return (self.llm_calls / self.total_jobs) if self.total_jobs > 0 else 0.0


class CostTracker:
    """資源與成本追蹤器。"""

    # 預設價格模型 (以 GPT-4o-mini 或 Gemini 1.5 Flash 為基準, 每百萬 token USD)
    DEFAULT_INPUT_PRICE_PER_M = 0.15
    DEFAULT_OUTPUT_PRICE_PER_M = 0.60

    def __init__(
        self,
        input_price_per_m: float = DEFAULT_INPUT_PRICE_PER_M,
        output_price_per_m: float = DEFAULT_OUTPUT_PRICE_PER_M,
    ):
        self.input_price_per_m = input_price_per_m
        self.output_price_per_m = output_price_per_m
        self.stats = CostStats()

    def record_job(self, latency_ms: float = 0.0):
        """記錄單一職缺處理完成。"""
        self.stats.total_jobs += 1
        self.stats.total_latency_ms += latency_ms

    def record_llm_call(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
        latency_ms: float = 0.0,
    ):
        """記錄單次 LLM / Verifier 調用。"""
        self.stats.llm_calls += 1
        self.stats.input_tokens += input_tokens
        self.stats.output_tokens += output_tokens
        self.stats.total_tokens += (input_tokens + output_tokens)
        self.stats.total_latency_ms += latency_ms

        # 計算費用
        call_cost = (
            (input_tokens / 1_000_000.0) * self.input_price_per_m
            + (output_tokens / 1_000_000.0) * self.output_price_per_m
        )
        self.stats.estimated_cost_usd += call_cost

    def get_summary(self) -> Dict[str, Any]:
        """回傳格式化統計摘要。"""
        return {
            "total_jobs": self.stats.total_jobs,
            "llm_calls": self.stats.llm_calls,
            "llm_call_rate": round(self.stats.llm_call_rate, 4),
            "input_tokens": self.stats.input_tokens,
            "output_tokens": self.stats.output_tokens,
            "total_tokens": self.stats.total_tokens,
            "total_latency_ms": round(self.stats.total_latency_ms, 2),
            "avg_latency_ms": round(self.stats.avg_latency_ms, 2),
            "estimated_cost_usd": round(self.stats.estimated_cost_usd, 6),
            "cost_per_1k_jobs_usd": round(self.stats.cost_per_1k_jobs_usd, 4),
        }

    def reset(self):
        """重設統計數據。"""
        self.stats = CostStats()
