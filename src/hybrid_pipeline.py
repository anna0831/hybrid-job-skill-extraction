"""Hybrid 職缺技能擷取管線：整合 AC 候選生成、風險分流路由與 LLM 上下文驗證。"""

import logging
import time
from typing import List, Dict, Any, Optional, Tuple, Callable
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
from src.utils.progress import ProgressTracker, ProgressSnapshot

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
        bypass_verification: bool = False,
        disable_retrieval: bool = False,
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

        # 4. 初始化 Phase 5/6 殘差語意召回引擎 (Residual Semantic Recovery Engine)
        self.enable_fn_recovery = enable_fn_recovery
        self.grounder: BaseConceptGrounder = get_concept_grounder(
            provider=grounder_provider,
            skill_id_index=skill_index,
            term_to_entries=term_to_entries,
        )
        from src.recovery.semantic_recovery import ResidualSemanticRecoveryEngine
        from src.verifier.semantic_verifier import SemanticVerifier
        self.semantic_verifier = SemanticVerifier(skill_id_index=skill_index)
        self.residual_engine = ResidualSemanticRecoveryEngine(
            skill_id_index=skill_index,
            verifier=self.semantic_verifier,
            bypass_verification=bypass_verification,
            disable_retrieval=disable_retrieval,
        )

        self.cat9_mapping = load_cat9_mapping(rules_path)

    def extract_job_skills(
        self,
        job_id: str,
        job_title: str,
        job_desc: str,
        tools: str = "",
        job_skills: str = "",
    ) -> Tuple[List[CandidateSkill], JobRoutingResult, List[VerificationResult]]:
        """處理單篇職缺，回傳 (最終保留技能, 分流決策結果, LLM驗證紀錄)。"""
        texts = [clean_text(job_desc), clean_text(job_skills), clean_text(tools)]
        clean_title = clean_text(job_title)

        # 步驟 1 (Stage A): AC 高召回匹配
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

        # 步驟 3 (Stage B): 第二軌上下文驗證 (僅對高風險或語意衝突候選詞呼叫)
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

        # 步驟 4: 合併 AC 驗證後技能 (verified_ac_skills)
        verified_ac_skills: List[CandidateSkill] = []
        for cand in routing_res.pass_through_candidates:
            verified_ac_skills.append(cand)
        for cand in routing_res.verify_candidates:
            if cand.skill_id not in rejected_ids:
                verified_ac_skills.append(cand)

        # 步驟 5 (Stage C-E): 殘差語意技能召回 (Residual Semantic Recovery)
        # 關鍵重構：不再只對 skill_count == 0 執行，而是對所有未被完全覆蓋之職缺執行殘差單元分析
        recovered_skills: List[CandidateSkill] = []
        fn_recovery_res: Optional[FNRecoveryResult] = None

        if self.enable_fn_recovery:
            # 執行 Stage C-E 殘差召回
            res_result = self.residual_engine.recover_residuals(
                job_id=job_id,
                job_title=clean_title,
                job_desc=texts[0],
                ac_matches=verified_ac_skills,
                tools=texts[2],
                job_skills=texts[1],
            )
            recovered_skills = res_result.recovered_skills

            if not self.residual_engine.disable_retrieval:
                # 兼容既有 fn_recovery_res 格式以支援審核總表
                fn_recovery_res = self.grounder.recover_job_skills(
                    job_id=job_id,
                    job_title=clean_title,
                    job_desc=texts[0],
                    tools=texts[2],
                    job_skills=texts[1],
                    existing_candidate_texts=[c.matched_keyword for c in candidates],
                )
                # 確保殘差召回的技能同步加入
                for r_cand in recovered_skills:
                    if r_cand.skill_id not in fn_recovery_res.recovered_skill_ids:
                        fn_recovery_res.recovered_skill_ids.append(r_cand.skill_id)

        # 步驟 6: 最終聚合技能 (Final Hybrid Skills = Verified AC + Recovered)
        final_skills: List[CandidateSkill] = list(verified_ac_skills)
        existing_ids = set(s.skill_id for s in final_skills)

        # 加入殘差引擎召回技能
        for r_cand in recovered_skills:
            if r_cand.skill_id not in existing_ids:
                final_skills.append(r_cand)
                existing_ids.add(r_cand.skill_id)

        # 同步加入概念接地器召回技能 (包含 Mock / Domain 映射技能)
        if fn_recovery_res and fn_recovery_res.recovered_skill_ids:
            for s_id in fn_recovery_res.recovered_skill_ids:
                if s_id in self.matcher.skill_index and s_id not in existing_ids:
                    s_dict = self.matcher.skill_index[s_id]
                    final_skills.append(
                        CandidateSkill(
                            skill_id=s_dict["SKILL_ID"],
                            skill_name=s_dict["SKILL_NAME"],
                            skill_name_zh=s_dict["SKILL_NAME_ZH"],
                            skill_type=s_dict.get("SKILL_TYPE", "Hard Skill"),
                            skill_cat9=s_dict.get("SKILL_CAT9", "Unclassified"),
                            category_code=s_dict.get("SKILL_CATEGORY", "0"),
                            category_name=s_dict.get("SKILL_CATEGORY_NAME", ""),
                            subcategory_code=s_dict.get("SKILL_SUBCATEGORY", "0"),
                            subcategory_name=s_dict.get("SKILL_SUBCATEGORY_NAME", ""),
                            is_software=s_dict.get("IS_SOFTWARE", False),
                            matched_keyword=f"[FN:{s_dict['SKILL_NAME_ZH']}]",
                            field_source="FN_RECOVERY",
                        )
                    )
                    existing_ids.add(s_id)

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
        self,
        df: pd.DataFrame,
        county: str = "unknown",
        month: str = "unknown",
        progress_callback: Optional[Callable[[ProgressSnapshot], None]] = None,
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
        total_jobs = len(df)

        tracker = ProgressTracker()
        tracker.start(total=total_jobs, initial_stage=ProgressTracker.STAGE_AC_MATCHING)
        if progress_callback:
            init_snap = tracker.update(0, stage=ProgressTracker.STAGE_AC_MATCHING, force=True)
            if init_snap:
                progress_callback(init_snap)

        for i, row in df.iterrows():
            t_job_start = time.time()
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

            job_latency = time.time() - t_job_start
            current_stage = (
                ProgressTracker.STAGE_RESIDUAL_RECOVERY
                if (self.enable_fn_recovery and routing_res.needs_fn_recovery)
                else ProgressTracker.STAGE_AC_MATCHING
            )

            if progress_callback:
                snap = tracker.update(
                    processed=i + 1,
                    stage=current_stage,
                    job_latency_sec=job_latency,
                )
                if snap:
                    progress_callback(snap)

        # 彙整與寬表格聚合階段
        if progress_callback:
            agg_snap = tracker.update(
                processed=total_jobs,
                stage=ProgressTracker.STAGE_AGGREGATING,
                force=True,
            )
            if agg_snap:
                progress_callback(agg_snap)

        # 自動產出/更新審核表與候選關鍵字
        if fn_results:
            try:
                self.export_keyword_candidates(fn_results)
            except Exception as e:
                logger.warning(f"自動匯出關鍵字候選失敗: {e}")

        long_df = pd.DataFrame(records)
        wide_df = skills_to_wide(long_df, df, cat9_mapping=self.cat9_mapping)
        stats = self.router.get_global_stats()

        if progress_callback:
            final_snap = tracker.finish()
            progress_callback(final_snap)

        return long_df, wide_df, stats
