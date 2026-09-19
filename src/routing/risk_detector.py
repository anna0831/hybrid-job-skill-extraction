"""風險特徵偵測器模組 (Risk Detector)。

負責對單一候選技能與職缺上下文進行多維度語意衝突檢測，
計算風險分數 (Risk Score) 並產生可解釋的風險觸發原因。
"""

import os
import yaml
import logging
from typing import List, Tuple, Dict, Any, Optional
from src.lexicon.schema import CandidateSkill

logger = logging.getLogger(__name__)


class RiskDetector:
    """候選技能語意衝突與風險量化偵測器。"""

    def __init__(self, rules_path: str = "configs/rules.yaml"):
        self.rules_path = rules_path
        self._load_rules()

    def _load_rules(self):
        """從設定檔載入風險關鍵字與語意特徵詞。"""
        if not os.path.exists(self.rules_path):
            logger.warning(f"找不到規則檔 {self.rules_path}，使用內建模認特徵規則")
            routing_cfg = {}
        else:
            with open(self.rules_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            routing_cfg = cfg.get("routing_rules", {})

        self.risk_threshold = float(routing_cfg.get("risk_threshold", 0.5))
        self.risky_keywords = set(
            routing_cfg.get(
                "risky_keywords",
                ["清潔", "研究", "月薪", "底薪", "薪資", "教育訓練", "訓練", "溝通", "管理", "維護", "操作"],
            )
        )
        self.benefit_markers = list(
            routing_cfg.get(
                "benefit_markers",
                ["底薪", "月薪", "薪資", "待遇", "年終", "全勤", "供餐", "員工旅遊", "提供教育訓練", "勞健保"],
            )
        )
        self.academic_markers = list(
            routing_cfg.get(
                "academic_markers",
                ["研究所", "大學畢業", "碩士以上", "博士學位", "學士"],
            )
        )
        self.collaborator_markers = list(
            routing_cfg.get(
                "collaborator_markers",
                ["配合後端", "配合前端", "與後端", "與前端", "後端 Python", "協助工程師"],
            )
        )
        self.high_trust_sources = set(
            routing_cfg.get("high_trust_sources", ["工作技能", "擅長工具", "工具欄"])
        )

    def evaluate(
        self,
        candidate: CandidateSkill,
        job_title: str,
        job_desc: str,
        tools: str = "",
        job_skills: str = "",
    ) -> Tuple[float, List[str]]:
        """評估單一候選技能之風險分數與觸發原因。
        
        回傳: (risk_score, risk_reasons)
        """
        score = 0.0
        reasons: List[str] = []
        kw = candidate.matched_keyword.strip()
        full_text = f"{job_title} {job_desc}"

        # 1. 高風險歧義關鍵字檢驗
        if kw in self.risky_keywords:
            score += 0.45
            reasons.append(f"命中高風險歧義關鍵字: '{kw}'")

        # 2. 薪資福利語境衝突檢驗 (GOLD_002 案型)
        if any(term in candidate.skill_name_zh for term in ["薪資", "薪酬", "訓練", "發展"]):
            has_benefit = any(b in full_text for b in self.benefit_markers)
            is_hr_role = any(r in job_title for r in ["人資", "薪酬", "招募", "培訓", "HR"])
            if has_benefit and not is_hr_role:
                score += 0.50
                reasons.append("技能名稱涉及薪酬/培訓，但職缺出現福利待遇描述且非人資職位")

        # 3. 學歷機構語境衝突檢驗 (GOLD_003 案型)
        if "研究" in candidate.skill_name_zh:
            has_academic = any(a in full_text for a in self.academic_markers)
            is_rd_role = any(r in job_title for r in ["研發", "研究員", "演算法", "科學家", "R&D"])
            if has_academic and not is_rd_role:
                score += 0.50
                reasons.append("命中『研究』技能，但職缺語境出現學歷要求（研究所）且非研發角色")

        # 4. 5S 清潔與環境維持衝突檢驗 (GOLD_003 案型)
        if "清潔" in candidate.skill_name_zh:
            is_cleaning_role = any(r in job_title for r in ["清潔員", "房務", "打掃", "家事"])
            has_5s = any(s in full_text for s in ["整潔清潔", "保持整潔", "維護清潔", "環境整潔", "5S"])
            if has_5s and not is_cleaning_role:
                score += 0.50
                reasons.append("命中『清潔』技能，但職缺語境為 5S 日常環境維持且非專業清潔職位")

        # 5. 跨部門協作者職稱衝突檢驗 (GOLD_014 案型)
        kw_lower = kw.lower()
        if "前端" in job_title and ("python" in kw_lower or "後端" in kw_lower or "後端" in candidate.skill_name_zh):
            score += 0.55
            reasons.append(f"職位為前端工程，但命中後端技術 '{kw}'")
        else:
            for cm in self.collaborator_markers:
                if cm.lower() in full_text.lower():
                    score += 0.35
                    reasons.append(f"文中出現跨團隊協作特徵: '{cm}'")
                    break

        # 6. 短字串無邊界歧義加成
        if len(kw) <= 2 and candidate.field_source in ["職位描述", "就近文意"]:
            score += 0.15
            reasons.append("職位描述中之 2 字短詞，具備潛在幾何撞詞風險")

        # 7. 高信賴度結構化欄位減免 (信用放行)
        if candidate.field_source in self.high_trust_sources:
            score -= 0.40
            reasons.append(f"來自高信賴度結構化欄位 ({candidate.field_source})，大幅降低風險")

        # 邊界約束
        score = max(0.0, min(1.0, score))
        return score, reasons
