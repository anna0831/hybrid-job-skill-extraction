"""LLM Provider 具體實作模組。

包含：
1. MockLLMVerifier: 確定性本地 Mock 驗證器，用於單元測試、CI/CD 及離線展示
2. OpenAIVerifier: 相容 OpenAI API 協議的實作 (可對接 GPT-4o-mini, Claude, vLLM, Ollama)
3. get_llm_verifier: 統一工廠函數
"""

import os
import json
import logging
import urllib.request
import urllib.error
from typing import List, Dict, Any, Optional

from src.llm_verifier.base import BaseLLMVerifier
from src.llm_verifier.cache import LLMCache
from src.llm_verifier.schemas import LLMVerdict

logger = logging.getLogger(__name__)


class MockLLMVerifier(BaseLLMVerifier):
    """確定性本地 Mock 驗證器。
    
    支援常見假陽性（福利薪資、5S清潔、學歷研究所、協作者語言）消歧，
    供本地測試、離線 Benchmark 與無 API Key 環境使用。
    """

    def __init__(
        self,
        model_name: str = "mock-verifier-v1",
        cache: Optional[LLMCache] = None,
        **kwargs,
    ):
        super().__init__(model_name=model_name, cache=cache, **kwargs)

    def _call_llm_api(self, messages: List[Dict[str, str]]) -> str:
        """模擬 LLM 邏輯推理，解析最後一則訊息之候選項目並產出驗證 JSON。"""
        last_message = messages[-1]["content"]
        # 擷取最後的 JSON 輸入
        start_idx = last_message.find("{")
        end_idx = last_message.rfind("}")
        if start_idx == -1 or end_idx == -1:
            return json.dumps({"results": []})

        try:
            query = json.loads(last_message[start_idx : end_idx + 1])
        except Exception:
            return json.dumps({"results": []})

        job_title = query.get("job_title", "")
        job_desc = query.get("job_desc", "")
        candidates = query.get("candidates", [])

        results = []
        full_text = f"{job_title} {job_desc}"

        for cand in candidates:
            skill_id = cand.get("skill_id", "")
            skill_name_zh = cand.get("skill_name_zh", "")
            matched_kw = cand.get("matched_keyword", "")

            # 尋找包含 matched_kw 的原始子句子作為 evidence
            evidence = self._find_evidence_sentence(full_text, matched_kw)

            # 規則 1: 薪資福利排除 (GOLD_002 假陽性)
            if skill_id == "KS120000000000000001" and ("月薪" in matched_kw or "底薪" in full_text) and ("薪酬" not in job_title and "人資" not in job_title):
                results.append({
                    "skill_id": skill_id,
                    "skill_name_zh": skill_name_zh,
                    "matched_keyword": matched_kw,
                    "ac_match": True,
                    "llm_verdict": LLMVerdict.REJECT.value,
                    "confidence": 0.98,
                    "evidence": evidence or matched_kw,
                    "reason": "文中出現金額薪資，屬於求職者福利待遇，非薪資管理專業職能。",
                })
            # 規則 2: 員工教育訓練福利排除 (GOLD_002 假陽性)
            elif skill_id == "KS120000000000000002" and ("教育訓練" in matched_kw) and ("訓練" not in job_title and "人資" not in job_title):
                results.append({
                    "skill_id": skill_id,
                    "skill_name_zh": skill_name_zh,
                    "matched_keyword": matched_kw,
                    "ac_match": True,
                    "llm_verdict": LLMVerdict.REJECT.value,
                    "confidence": 0.95,
                    "evidence": evidence or matched_kw,
                    "reason": "公司為員工提供之在職進修福利，非本職缺應徵條件之專業訓練規劃技能。",
                })
            # 規則 3: 環境整潔清潔排除 (GOLD_003 假陽性)
            elif skill_id == "KS120000000000000006" and ("整潔清潔" in full_text or "保持整潔" in full_text) and ("清潔員" not in job_title and "房務" not in job_title):
                results.append({
                    "skill_id": skill_id,
                    "skill_name_zh": skill_name_zh,
                    "matched_keyword": matched_kw,
                    "ac_match": True,
                    "llm_verdict": LLMVerdict.REJECT.value,
                    "confidence": 0.96,
                    "evidence": evidence or matched_kw,
                    "reason": "一般作業場所之 5S 環境整潔維護，並非專業清潔打掃服務技術要求。",
                })
            # 規則 4: 研究所學歷排除 (GOLD_003 假陽性)
            elif skill_id == "KS120000000000000003" and ("研究所" in full_text) and ("研究員" not in job_title and "研發" not in job_title):
                results.append({
                    "skill_id": skill_id,
                    "skill_name_zh": skill_name_zh,
                    "matched_keyword": matched_kw,
                    "ac_match": True,
                    "llm_verdict": LLMVerdict.REJECT.value,
                    "confidence": 0.98,
                    "evidence": evidence or matched_kw,
                    "reason": "『研究所』代表學歷教育機構，並非科學研究專業技術職能。",
                })
            # 規則 5: 跨部門協作者語言排除 (GOLD_014 假陽性: Vue 前端中出現後端 Python 工程師)
            elif skill_id == "KS120000000000000007" and "前端" in job_title and ("後端 python" in full_text.lower() or "python 工程師" in full_text.lower() or "python" in full_text.lower()):
                results.append({
                    "skill_id": skill_id,
                    "skill_name_zh": skill_name_zh,
                    "matched_keyword": matched_kw,
                    "ac_match": True,
                    "llm_verdict": LLMVerdict.REJECT.value,
                    "confidence": 0.95,
                    "evidence": evidence or matched_kw,
                    "reason": "Python 屬於跨團隊協作對象之職稱專長，應徵者為前端工程師，無需具備後端 Python 開發能力。",
                })
            # 規則 6: 真實技能確認 (KEEP)
            elif matched_kw in full_text:
                results.append({
                    "skill_id": skill_id,
                    "skill_name_zh": skill_name_zh,
                    "matched_keyword": matched_kw,
                    "ac_match": True,
                    "llm_verdict": LLMVerdict.KEEP.value,
                    "confidence": 0.92,
                    "evidence": evidence or matched_kw,
                    "reason": f"符合職缺『{job_title}』要求之工作能力與專業技能。",
                })
            # 規則 7: 無法確認 (UNCERTAIN)
            else:
                results.append({
                    "skill_id": skill_id,
                    "skill_name_zh": skill_name_zh,
                    "matched_keyword": matched_kw,
                    "ac_match": True,
                    "llm_verdict": LLMVerdict.UNCERTAIN.value,
                    "confidence": 0.5,
                    "evidence": "",
                    "reason": "未在職缺內文中找到充分依據，標記為 UNCERTAIN。",
                })

        return json.dumps({"results": results}, ensure_ascii=False)

    @staticmethod
    def _find_evidence_sentence(text: str, keyword: str) -> str:
        """從文本中切分並尋找包含關鍵字的句子，作為原文佐證。"""
        if not keyword or keyword not in text:
            return ""
        # 以標點切句
        delimiters = ["。", "；", "！", "!", "\n", "，", ","]
        import re
        parts = re.split(r"[。；！!\n]", text)
        for part in parts:
            if keyword in part:
                return part.strip()
        return keyword


class OpenAIVerifier(BaseLLMVerifier):
    """相容 OpenAI 協定之 API 驗證器。
    
    支援 OpenAI (gpt-4o-mini)、Anthropic API 橋接器，
    或本地 vLLM / Ollama (`http://localhost:11434/v1`)。
    """

    def __init__(
        self,
        model_name: str = "gpt-4o-mini",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        cache: Optional[LLMCache] = None,
        timeout: float = 30.0,
        **kwargs,
    ):
        super().__init__(model_name=model_name, cache=cache, **kwargs)
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.base_url = (
            base_url
            or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        ).rstrip("/")
        self.timeout = timeout

    def _call_llm_api(self, messages: List[Dict[str, str]]) -> str:
        """透過標準庫 HTTP 請求呼叫 OpenAI 相容端點。"""
        if not self.api_key and "localhost" not in self.base_url:
            raise ValueError(
                "未設定 OPENAI_API_KEY，無法呼叫外部 API。請設置環境變數或改用 MockLLMVerifier。"
            )

        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
        }

        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                resp_body = resp.read().decode("utf-8")
                res_data = json.loads(resp_body)
                choices = res_data.get("choices", [])
                if choices and "message" in choices[0]:
                    return choices[0]["message"].get("content", "{}")
                return "{}"
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            logger.error(f"OpenAI API 請求失敗 (HTTP {e.code}): {err_body}")
            raise RuntimeError(f"OpenAI API 錯誤 {e.code}: {err_body}")
        except Exception as e:
            logger.error(f"連線 OpenAI 相容端點失敗: {e}")
            raise


def get_llm_verifier(
    provider: str = "mock",
    model_name: Optional[str] = None,
    cache: Optional[LLMCache] = None,
    **kwargs,
) -> BaseLLMVerifier:
    """LLM 驗證器工廠函數。
    
    參數：
    - provider: "mock" (預設) 或 "openai"
    - model_name: 指定模型名稱 (預設: mock -> mock-verifier-v1, openai -> gpt-4o-mini)
    - cache: LLMCache 實例 (若為 None 則不啟用快取)
    """
    provider_lower = provider.lower().strip()
    if provider_lower == "mock":
        name = model_name or "mock-verifier-v1"
        return MockLLMVerifier(model_name=name, cache=cache, **kwargs)
    elif provider_lower in ["openai", "chatgpt", "vllm", "ollama"]:
        name = model_name or "gpt-4o-mini"
        return OpenAIVerifier(model_name=name, cache=cache, **kwargs)
    else:
        raise ValueError(f"不支援的 LLM Provider: '{provider}'，支援列表: ['mock', 'openai']")
