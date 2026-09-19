"""本地 SQLite 呼叫快取模組：避免重複呼叫 LLM API，控制研發與測試成本。"""

import os
import sqlite3
import hashlib
import json
import logging
from typing import Optional, Dict, Any, List, Tuple
from src.llm_verifier.schemas import VerificationResult, LLMVerdict
from src.lexicon.schema import CandidateSkill

logger = logging.getLogger(__name__)


class LLMCache:
    """以 SQLite 實現的執行期快取管理類別。"""

    def __init__(self, db_path: str = "outputs/llm_cache.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._init_db()
        self.hit_count = 0
        self.miss_count = 0

    def _init_db(self):
        """初始化資料表結構。"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS llm_verification_cache (
                    cache_key TEXT PRIMARY KEY,
                    job_title TEXT,
                    skill_id TEXT,
                    matched_keyword TEXT,
                    model_name TEXT,
                    verdict TEXT,
                    confidence REAL,
                    evidence TEXT,
                    reason TEXT,
                    raw_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()

    @staticmethod
    def generate_key(
        job_title: str,
        job_desc: str,
        skill_id: str,
        matched_keyword: str,
        model_name: str,
    ) -> str:
        """根據職缺內容、技能代碼與模型名稱生成唯一雜湊金鑰。"""
        raw_str = f"{job_title.strip()}|||{job_desc.strip()}|||{skill_id.strip()}|||{matched_keyword.strip()}|||{model_name.strip()}"
        return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()

    def get(
        self,
        job_title: str,
        job_desc: str,
        skill_id: str,
        matched_keyword: str,
        model_name: str,
    ) -> Optional[VerificationResult]:
        """從快取查詢單一候選技能之驗證結果。"""
        key = self.generate_key(job_title, job_desc, skill_id, matched_keyword, model_name)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT raw_json FROM llm_verification_cache WHERE cache_key = ?",
                (key,),
            )
            row = cursor.fetchone()
            if row and row[0]:
                self.hit_count += 1
                data = json.loads(row[0])
                return VerificationResult(**data)
            else:
                self.miss_count += 1
                return None

    def put(
        self,
        job_title: str,
        job_desc: str,
        result: VerificationResult,
        model_name: str,
    ):
        """將單筆驗證結果寫入快取。"""
        key = self.generate_key(
            job_title, job_desc, result.skill_id, result.matched_keyword, model_name
        )
        raw_json = json.dumps(result.to_dict(), ensure_ascii=False)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO llm_verification_cache
                (cache_key, job_title, skill_id, matched_keyword, model_name, verdict, confidence, evidence, reason, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    key,
                    job_title,
                    result.skill_id,
                    result.matched_keyword,
                    model_name,
                    result.llm_verdict.value,
                    result.confidence,
                    result.evidence,
                    result.reason,
                    raw_json,
                ),
            )
            conn.commit()

    def filter_cached(
        self,
        job_title: str,
        job_desc: str,
        candidates: List[CandidateSkill],
        model_name: str,
    ) -> Tuple[List[VerificationResult], List[CandidateSkill]]:
        """批次過濾快取：將候選詞拆分為已命中快取與未命中快取兩組。
        
        回傳：(cached_results, uncached_candidates)
        """
        cached_results: List[VerificationResult] = []
        uncached_candidates: List[CandidateSkill] = []

        for cand in candidates:
            cached = self.get(
                job_title=job_title,
                job_desc=job_desc,
                skill_id=cand.skill_id,
                matched_keyword=cand.matched_keyword,
                model_name=model_name,
            )
            if cached is not None:
                cached_results.append(cached)
            else:
                uncached_candidates.append(cand)

        return cached_results, uncached_candidates

    def stats(self) -> Dict[str, Any]:
        """回傳目前快取統計數據。"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM llm_verification_cache")
            total_records = cursor.fetchone()[0]

        total_requests = self.hit_count + self.miss_count
        hit_rate = (self.hit_count / total_requests) if total_requests > 0 else 0.0

        return {
            "total_cached_records": total_records,
            "hit_count": self.hit_count,
            "miss_count": self.miss_count,
            "hit_rate": round(hit_rate, 4),
        }

    def clear(self):
        """清空快取資料表。"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM llm_verification_cache")
            conn.commit()
        self.hit_count = 0
        self.miss_count = 0
