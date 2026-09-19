"""LLM Verification Layer: 候選技能語意消歧與上下文驗證模組。"""

from src.llm_verifier.schemas import (
    LLMVerdict,
    VerificationResult,
    BatchVerificationResponse,
)
from src.llm_verifier.cache import LLMCache
from src.llm_verifier.base import BaseLLMVerifier
from src.llm_verifier.providers import (
    MockLLMVerifier,
    OpenAIVerifier,
    get_llm_verifier,
)
from src.llm_verifier.prompts import (
    SYSTEM_PROMPT,
    FEW_SHOT_EXAMPLES,
    build_verification_prompt,
)

__all__ = [
    "LLMVerdict",
    "VerificationResult",
    "BatchVerificationResponse",
    "LLMCache",
    "BaseLLMVerifier",
    "MockLLMVerifier",
    "OpenAIVerifier",
    "get_llm_verifier",
    "SYSTEM_PROMPT",
    "FEW_SHOT_EXAMPLES",
    "build_verification_prompt",
]
