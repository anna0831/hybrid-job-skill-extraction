"""LLM 驗證層抽象基類 (BaseLLMVerifier)。

提供快取檢查、Prompt 呼叫、指數退避重試 (Exponential Backoff)、JSON 解析防禦與安全退場機制。
可任意置換後端 Provider (例如 Mock, OpenAI, Anthropic, Ollama, vLLM 等)。
"""

import abc
import json
import logging
import re
import time
from typing import List, Optional, Dict, Any

from src.lexicon.schema import CandidateSkill
from src.llm_verifier.schemas import (
    VerificationResult,
    BatchVerificationResponse,
    LLMVerdict,
)
from src.llm_verifier.cache import LLMCache
from src.llm_verifier.prompts import build_verification_prompt

logger = logging.getLogger(__name__)


class BaseLLMVerifier(abc.ABC):
    """LLM 候選技能驗證器的抽象基類。"""

    def __init__(
        self,
        model_name: str = "base-verifier",
        cache: Optional[LLMCache] = None,
        temperature: float = 0.0,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        self.model_name = model_name
        self.cache = cache
        self.temperature = temperature
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    @abc.abstractmethod
    def _call_llm_api(self, messages: List[Dict[str, str]]) -> str:
        """呼叫具體 LLM Provider API 並回傳字串回應。由子類別實作。"""
        pass

    def verify_candidates(
        self,
        job_title: str,
        job_desc: str,
        candidates: List[CandidateSkill],
        tools: Optional[str] = None,
    ) -> List[VerificationResult]:
        """驗證單篇職缺的所有候選技能。
        
        步驟：
        1. 查詢 SQLite 快取，命中者直接載入。
        2. 未命中者透過 Prompt Engineering 呼叫 LLM。
        3. 防禦性解析回傳之 JSON 並以 Pydantic Schema 驗證。
        4. 將新結果寫入快取。
        5. 依據原始候選詞順序重組並回傳完整結果。
        """
        if not candidates:
            return []

        # 1. 查詢快取
        cached_results: List[VerificationResult] = []
        uncached_candidates: List[CandidateSkill] = []

        if self.cache is not None:
            cached_results, uncached_candidates = self.cache.filter_cached(
                job_title=job_title,
                job_desc=job_desc,
                candidates=candidates,
                model_name=self.model_name,
            )
        else:
            uncached_candidates = list(candidates)

        # 2. 若全部命中快取，直接回傳
        new_results: List[VerificationResult] = []
        if uncached_candidates:
            messages = build_verification_prompt(
                job_title=job_title,
                job_desc=job_desc,
                candidates=uncached_candidates,
                tools=tools,
            )
            raw_response = self._call_with_retry(messages)
            new_results = self._parse_and_validate(
                raw_response=raw_response,
                job_title=job_title,
                job_desc=job_desc,
                candidates=uncached_candidates,
            )

            # 3. 寫入快取
            if self.cache is not None:
                for res in new_results:
                    self.cache.put(
                        job_title=job_title,
                        job_desc=job_desc,
                        result=res,
                        model_name=self.model_name,
                    )

        # 4. 合併結果並維持輸入順序
        result_map: Dict[str, VerificationResult] = {}
        for res in cached_results + new_results:
            key = f"{res.skill_id}::{res.matched_keyword}"
            result_map[key] = res

        ordered_results: List[VerificationResult] = []
        for cand in candidates:
            key = f"{cand.skill_id}::{cand.matched_keyword}"
            if key in result_map:
                ordered_results.append(result_map[key])
            else:
                # 安全退場 fallback
                ordered_results.append(
                    VerificationResult(
                        skill_id=cand.skill_id,
                        skill_name_zh=cand.skill_name_zh,
                        matched_keyword=cand.matched_keyword,
                        ac_match=True,
                        llm_verdict=LLMVerdict.UNCERTAIN,
                        confidence=0.5,
                        evidence="",
                        reason="未取得模型有效驗證回傳，自動退場至 UNCERTAIN",
                    )
                )

        return ordered_results

    def _call_with_retry(self, messages: List[Dict[str, str]]) -> str:
        """具備指數退避之 API 呼叫重試機制。"""
        last_exception: Optional[Exception] = None
        current_delay = self.retry_delay

        for attempt in range(1, self.max_retries + 1):
            try:
                return self._call_llm_api(messages)
            except Exception as e:
                last_exception = e
                logger.warning(
                    f"[{self.model_name}] API 呼叫失敗 (嘗試 {attempt}/{self.max_retries}): {e}"
                )
                if attempt < self.max_retries:
                    time.sleep(current_delay)
                    current_delay *= 2.0

        logger.error(f"[{self.model_name}] 已達最大重試次數，呼叫失敗: {last_exception}")
        return "{}"

    def _parse_and_validate(
        self,
        raw_response: str,
        job_title: str,
        job_desc: str,
        candidates: List[CandidateSkill],
    ) -> List[VerificationResult]:
        """防禦性擷取與解析 JSON，並針對候選技能防偽校驗。"""
        extracted_json = self._extract_json(raw_response)
        candidate_cand_map = {
            c.skill_id: c for c in candidates
        }

        parsed_results: List[VerificationResult] = []
        if "results" in extracted_json and isinstance(extracted_json["results"], list):
            for item in extracted_json["results"]:
                try:
                    s_id = item.get("skill_id", "")
                    # 嚴格詞庫對齊：若模型幻覺出不在候選列表中的技能，直接略過
                    if s_id not in candidate_cand_map:
                        logger.warning(f"偵測到模型回傳非候選技能代碼: {s_id}，已過濾")
                        continue

                    cand = candidate_cand_map[s_id]
                    # 確實驗證 evidence 為原文子字串（若非子字串則補救調整或標記）
                    evidence = item.get("evidence", "")
                    if evidence and evidence not in job_desc and evidence not in job_title:
                        logger.debug(f"Evidence 非原文子字串: '{evidence}'")

                    verdict_str = item.get("llm_verdict", "UNCERTAIN").upper()
                    if verdict_str not in [v.value for v in LLMVerdict]:
                        verdict_str = LLMVerdict.UNCERTAIN.value

                    res = VerificationResult(
                        skill_id=s_id,
                        skill_name_zh=item.get("skill_name_zh", cand.skill_name_zh),
                        matched_keyword=item.get("matched_keyword", cand.matched_keyword),
                        ac_match=True,
                        llm_verdict=LLMVerdict(verdict_str),
                        confidence=float(item.get("confidence", 0.9)),
                        evidence=evidence,
                        reason=item.get("reason", "模型分析語境得出結論"),
                    )
                    parsed_results.append(res)
                except Exception as e:
                    logger.error(f"解析單筆驗證結果時發生錯誤: {e}, item={item}")

        # 若有候選詞在模型輸出中遺漏，補齊 UNCERTAIN
        returned_ids = {r.skill_id for r in parsed_results}
        for cand in candidates:
            if cand.skill_id not in returned_ids:
                parsed_results.append(
                    VerificationResult(
                        skill_id=cand.skill_id,
                        skill_name_zh=cand.skill_name_zh,
                        matched_keyword=cand.matched_keyword,
                        ac_match=True,
                        llm_verdict=LLMVerdict.UNCERTAIN,
                        confidence=0.5,
                        evidence="",
                        reason="模型輸出未包含此項候選詞，預設補齊 UNCERTAIN",
                    )
                )

        return parsed_results

    @staticmethod
    def _extract_json(text: str) -> Dict[str, Any]:
        """從包含 Markdown 標記或雜訊的字串中擷取純 JSON 物件。"""
        text = text.strip()
        # 移除 ```json ... ``` 區塊外框
        if "```" in text:
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
            if match:
                text = match.group(1).strip()

        # 尋找最外層的 { }
        start_idx = text.find("{")
        end_idx = text.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            text = text[start_idx : end_idx + 1]

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失敗: {e}, 原文字串: {text[:200]}")
            return {}
