"""Hybrid 職缺技能擷取管線：整合 AC 候選生成、風險分流路由與 LLM 上下文驗證。"""

import logging
import time
from typing import List, Dict, Any, Optional, Tuple
import pandas as pd

from src.lexicon.loader import LexiconLoader
from src.ac_matcher.engine import ACMatcher
from src.routing.router import RiskBasedRouter
from src.routing.schemas import JobRoutingResult
from src.llm_verifier.base import BaseLLMVerifier
from src.llm_verifier.providers import get_llm_verifier
from src.llm_verifier.cache import LLMCache
from src.llm_verifier.schemas import LLMVerdict, VerificationResult
from src.lexicon.schema import CandidateSkill
from src.grounding.providers import get_concept_grounder, BaseConceptGrounder
from src.grounding.schemas import FNRecoveryResult
from src.preprocessing.normalizer import clean_text, extract_county, extract_month
from src.outputs.formatter import skills_to_wide, load_cat9_mapping

logger = logging.getLogger(__name__)


class HybridJobSkillPipeline:
    """混合式職缺技能擷取管線。
    
    執行流程：
    1. AC 候選詞生成 (High Recall Candidate Generation)
    2. 三軌風險分流 (Risk-based Routing):
       - Track 1: 直通放行 (PASS_THROUGH, 0 API 成本)
       - Track 2: 送入 LLM 驗證層 (VERIFY_CONTEXT, 消除 FP)
       - Track 3: 兩階段概念接地 (RECOVER_FN, Stage 1 Discovery + Stage 2 Lexicon Grounding)
    3. 結果整合與審計追蹤日誌 (Audit Trail)
    """

    def __init__(
        self,
        lexicon_path: str = "lexicon/sample/mini_skill_lexicon.csv",
        rules_path: str = "configs/rules.yaml",
        synonyms_path: str = "configs/synonyms.yaml",
        verifier_provider: str = "mock",
        grounder_provider: str = "mock",
        cache_db_path: str = "outputs/llm_cache.db",
        risk_threshold: Optional[float] = None,
        enable_cache: bool = True,
        enable_fn_recovery: bool = True,
    ):
        self.lexicon_path = lexicon_path
        self.rules_path = rules_path
        self.synonyms_path = synonyms_path

        # 1. 初始化 AC Matcher
        self.loader = LexiconLoader(rules_path=rules_path, synonyms_path=synonyms_path)
        term_to_entries, skill_index = self.loader.load_lexicon(lexicon_path)
        self.matcher = ACMatcher.build_from_lexicon(
            term_to_entries=term_to_entries,
            skill_index=skill_index,
            rules_path=rules_path,
        )

        # 2. 初始化風險路由器
        self.router = RiskBasedRouter(
            rules_path=rules_path, risk_threshold=risk_threshold
        )

        # 3. 初始化 LLM 驗證層
        self.cache = LLMCache(db_path=cache_db_path) if enable_cache else None
        self.verifier: BaseLLMVerifier = get_llm_verifier(
            provider=verifier_provider, cache=self.cache
        )

        # 4. 初始化 Phase 5 兩階段概念接地與假陰性召回器
        self.enable_fn_recovery = enable_fn_recovery
        self.grounder: BaseConceptGrounder = get_concept_grounder(
            provider=grounder_provider,
            skill_id_index=skill_index,
            term_to_entries=term_to_entries,
        )

        self.cat9_mapping = load_cat9_mapping(rules_path)

    def extract_job_skills(
        self,
        job_id: str,
        job_title: str,
        job_desc: str,
        tools: str = "",
        job_skills: str = "",
    ) -> Tuple[List[CandidateSkill], JobRoutingResult, List[VerificationResult], Optional[FNRecoveryResult]]:
        """處理單篇職缺，回傳 (最終保留技能, 分流決策結果, LLM驗證紀錄, FN召回紀錄)。"""
        texts = [clean_text(job_desc), clean_text(job_skills), clean_text(tools)]
        clean_title = clean_text(job_title)

        # 步驟 1: AC 高召回匹配
        candidates = self.matcher.extract_job_skills(texts, job_title=clean_title)

        # 步驟 2: 三軌分流
        routing_res = self.router.route_job(
            job_id=job_id,
            job_title=clean_title,
            job_desc=texts[0],
            candidates=candidates,
            tools=texts[2],
            job_skills=texts[1],
        )

        # 步驟 3: 第二軌 LLM 驗證 (僅對高風險候選詞呼叫)
        verification_records: List[VerificationResult] = []
        rejected_ids = set()

        if routing_res.verify_candidates:
            verification_records = self.verifier.verify_candidates(
                job_title=clean_title,
                job_desc=texts[0],
                candidates=routing_res.verify_candidates,
                tools=texts[2],
            )
            for v_res in verification_records:
                if v_res.llm_verdict == LLMVerdict.REJECT:
                    rejected_ids.add(v_res.skill_id)

        # 步驟 4: 合併最終技能清單 (第一軌直通放行 + 第二軌驗證通過)
        final_skills: List[CandidateSkill] = []

        # 第一軌直接加入
        final_skills.extend(routing_res.pass_through_candidates)

        # 第二軌過濾排除項後加入
        for cand in routing_res.verify_candidates:
            if cand.skill_id not in rejected_ids:
                final_skills.append(cand)

        # 步驟 5 (Phase 5): 第三軌兩階段概念接地與假陰性召回 (Track 3: FN Recovery)
        fn_recovery_res: Optional[FNRecoveryResult] = None
        if self.enable_fn_recovery and (routing_res.needs_fn_recovery or len(final_skills) == 0):
            fn_recovery_res = self.grounder.recover_job_skills(
                job_id=job_id,
                job_title=clean_title,
                job_desc=texts[0],
                tools=texts[2],
                job_skills=texts[1],
                existing_candidate_texts=[c.matched_keyword for c in candidates],
            )
            for s_id in fn_recovery_res.recovered_skill_ids:
                if s_id in self.matcher.skill_index:
                    s_dict = self.matcher.skill_index[s_id]
                    # 避免重複加入已存在的 skill_id
                    if any(c.skill_id == s_id for c in final_skills):
                        continue
                    recovered_cand = CandidateSkill(
                        skill_id=s_dict["SKILL_ID"],
                        skill_name=s_dict["SKILL_NAME"],
                        skill_name_zh=s_dict["SKILL_NAME_ZH"],
                        skill_type=s_dict["SKILL_TYPE"],
                        skill_cat9=s_dict["SKILL_CAT9"],
                        category_code=s_dict["SKILL_CATEGORY"],
                        category_name=s_dict["SKILL_CATEGORY_NAME"],
                        subcategory_code=s_dict["SKILL_SUBCATEGORY"],
                        subcategory_name=s_dict["SKILL_SUBCATEGORY_NAME"],
                        is_software=s_dict["IS_SOFTWARE"],
                        matched_keyword=f"[FN:{s_dict['SKILL_NAME_ZH']}]",
                        field_source="FN_RECOVERY",
                    )
                    final_skills.append(recovered_cand)

        routing_res.fn_recovery_result = fn_recovery_res
        return final_skills, routing_res, verification_records

    def diagnose_job_description(
        self,
        job_title: str,
        job_desc: str,
        tools: str = "",
        job_skills: str = "",
        job_id: str = "DIAGNOSTIC_JOB",
    ) -> FNRecoveryResult:
        """Task 1 專用：診斷單一職缺之假陰性短語並回傳完整對齊報告。"""
        texts = [clean_text(job_desc), clean_text(job_skills), clean_text(tools)]
        clean_title = clean_text(job_title)

        # 1. 執行 AC 匹配
        ac_cands = self.matcher.extract_job_skills(texts, job_title=clean_title)
        ac_keywords = [c.matched_keyword for c in ac_cands]

        # 2. 執行語意概念接地與假陰性診斷
        fn_res = self.grounder.recover_job_skills(
            job_id=job_id,
            job_title=clean_title,
            job_desc=texts[0],
            tools=texts[2],
            job_skills=texts[1],
            existing_candidate_texts=ac_keywords,
        )

        # 補充 AC 匹配結果標記
        for s_item in fn_res.semantic_items:
            s_item.ac_result = "None" if not ac_keywords else f"AC已匹配: {', '.join(ac_keywords)}"

        return fn_res

    def generate_review_table(
        self, fn_results: List[FNRecoveryResult]
    ) -> pd.DataFrame:
        """Task 5: 從 FNRecoveryResult 清單生成 Human Review Table。"""
        from src.grounding.review_table import build_review_table

        records = []
        for fn_res in fn_results:
            for s_item in fn_res.semantic_items:
                records.append({
                    "job_title": fn_res.job_title,
                    "item": s_item,
                })
        return build_review_table(records)

    def export_keyword_candidates(
        self,
        fn_results: List[FNRecoveryResult],
        output_path: str = "outputs/keyword_candidates.csv",
        confidence_threshold: float = 0.80,
    ) -> pd.DataFrame:
        """Task 6: 將高置信度 MATCH 項目輸出至 outputs/keyword_candidates.csv。"""
        from src.grounding.expansion import KeywordCandidateManager

        manager = KeywordCandidateManager(output_path=output_path)
        records = []
        for fn_res in fn_results:
            for s_item in fn_res.semantic_items:
                records.append({
                    "job_title": fn_res.job_title,
                    "item": s_item,
                    "discovery_method": "SEMANTIC_RECOVERY_HYBRID",
                })
        return manager.export_candidates(
            records=records, confidence_threshold=confidence_threshold
        )

    def process_dataframe(
        self, df: pd.DataFrame, county: str = "unknown", month: str = "unknown"
    ) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
        """批次處理 DataFrame，回傳 (long_df, wide_df, global_stats)。"""
        def find_col(candidates, default=""):
            for c in candidates:
                if c in df.columns:
                    return c
            return default

        id_col = find_col(["工作編號", "ID", "id"], default="id")
        tool_col = find_col(["擅長工具", "電腦工具", "tools"], default="tools")
        title_col = find_col(["職位名稱", "104職位名稱", "job_title"], default="job_title")
        desc_col = find_col(["職位描述", "job_desc"], default="job_desc")
        skill_col = find_col(["工作技能", "job_skills"], default="job_skills")

        records = []
        fn_results: List[FNRecoveryResult] = []

        for i, row in df.iterrows():
            job_id = str(row.get(id_col, f"JOB_{i}"))
            title = str(row.get(title_col, ""))
            desc = str(row.get(desc_col, ""))
            tools = str(row.get(tool_col, ""))
            skills = str(row.get(skill_col, ""))

            final_skills, routing_res, _ = self.extract_job_skills(
                job_id=job_id,
                job_title=title,
                job_desc=desc,
                tools=tools,
                job_skills=skills,
            )

            if routing_res.fn_recovery_result:
                fn_results.append(routing_res.fn_recovery_result)

            for cand in final_skills:
                records.append({
                    "ID": job_id,
                    "縣市": county,
                    "月份": month,
                    **cand.to_dict(),
                })

        # 自動產出/更新審核表與候選關鍵字
        if fn_results:
            try:
                self.export_keyword_candidates(fn_results)
            except Exception as e:
                logger.warning(f"自動匯出關鍵字候選失敗: {e}")

        long_df = pd.DataFrame(records)
        wide_df = skills_to_wide(long_df, df, cat9_mapping=self.cat9_mapping)
        stats = self.router.get_global_stats()
        return long_df, wide_df, stats
