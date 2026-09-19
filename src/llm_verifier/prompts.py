"""提示詞工程模組 (Prompt Engineering for LLM Verification Layer)。

包含：
1. 嚴格限定 Schema 與輸出的 System Prompt
2. 包含 Taiwanese 104 語境的 Few-Shot CoT 範例 (福利/薪資過濾、協作者語言、環境清潔消歧、真偽技能對照)
3. Prompt 組裝函數與輔助工具
"""

import json
from typing import List, Optional, Dict, Any
from src.lexicon.schema import CandidateSkill


SYSTEM_PROMPT = """你是一位精通台灣招聘市場（104人力銀行）與職業技能分類體系（Lightcast/O*NET）的資深 NLP 資訊擷取與語意消歧專家。

【任務目標】
接收經由字典樹（Aho-Corasick）高召回率匹配所產生的「候選技能列表（Candidate Skills）」與該篇職缺的「完整職缺內文（Job Title & Description）」。
請仔細研讀職缺語境，逐一驗證每個候選技能是否「確實為該職位所要求、具備或執行的專業技能/專業工具/軟實力」。

【判決標準 (LLMVerdict)】
1. KEEP (保留)：
   - 該候選詞在語境中確實代表該職位核心職責、工作技能、工具使用或必要條件。
   - 例：後端工程師職缺中「需具備 Python 爬蟲與 API 開發經驗」-> Python, API 開發 為 KEEP。
   - 例：飯店房務員職缺中「負責客房打掃與衛浴清潔」-> 清潔 為 KEEP。

2. REJECT (排除 - 假陽性 False Positive)：
   - 福利或薪酬描述：如「底薪 32,000 元，月薪 35,000 元」、「公司提供教育訓練」、「員工旅遊」中誤抓的「薪資管理」、「訓練與發展」。
   - 學歷或機構名稱：如「國內外大學研究所畢業」誤抓「研究」。
   - 環境與常規整潔：如製造業作業員「每日下班保持工作區域整潔清潔」誤抓「清潔」。
   - 跨部門協作者代稱：如 Vue 前端工程師職缺中「需與後端 Python 工程師協調」誤抓「Python」（Python 是協作者的技能，非本職缺應徵者技能）。
   - 普通名詞非技能指涉：關鍵字僅作為日常口語或無關語義出現。

3. UNCERTAIN (無法確定)：
   - 原文上下文極其簡短，或缺乏足夠線索判斷是否為技能要求。

【鐵律約束 (Hard Constraints)】
1. 絕不允許捏造 (No Hallucination)：嚴禁自行發明新技能或更改 skill_id 與 skill_name_zh。只能針對輸入之候選項目做出判定。
2. 證據原文引用 (Grounded Evidence)：evidence 欄位必須為職缺內文之「原始子字串引用」，嚴禁改寫或自行編造。
3. 嚴格 JSON 輸出：回傳內容必須完全符合 JSON 格式，不得包含任何 Markdown 外框（如 ```json ```）以外的閒聊字元。
"""

FEW_SHOT_EXAMPLES: List[Dict[str, Any]] = [
    {
        "job_title": "行政會計專員",
        "job_desc": "負責日常總務事務、會客登記與訪客接待。底薪 32,000 元，月薪 35,000 元含全勤。公司提供完整教育訓練與員工旅遊。",
        "candidates": [
            {
                "skill_id": "KS120000000000000011",
                "skill_name_zh": "會客登記",
                "matched_keyword": "會客登記",
            },
            {
                "skill_id": "KS120000000000000001",
                "skill_name_zh": "薪資管理",
                "matched_keyword": "月薪",
            },
            {
                "skill_id": "KS120000000000000002",
                "skill_name_zh": "訓練與發展",
                "matched_keyword": "教育訓練",
            },
        ],
        "response": {
            "results": [
                {
                    "skill_id": "KS120000000000000011",
                    "skill_name_zh": "會客登記",
                    "matched_keyword": "會客登記",
                    "ac_match": True,
                    "llm_verdict": "KEEP",
                    "confidence": 0.98,
                    "evidence": "負責日常總務事務、會客登記與訪客接待",
                    "reason": "行政職缺核心日常工作職責，為明確工作專業技能。",
                },
                {
                    "skill_id": "KS120000000000000001",
                    "skill_name_zh": "薪資管理",
                    "matched_keyword": "月薪",
                    "ac_match": True,
                    "llm_verdict": "REJECT",
                    "confidence": 0.99,
                    "evidence": "底薪 32,000 元，月薪 35,000 元含全勤",
                    "reason": "『月薪』屬於求職者薪資福利待遇條款，並非人資或財務之薪資管理技能要求，屬假陽性。",
                },
                {
                    "skill_id": "KS120000000000000002",
                    "skill_name_zh": "訓練與發展",
                    "matched_keyword": "教育訓練",
                    "ac_match": True,
                    "llm_verdict": "REJECT",
                    "confidence": 0.95,
                    "evidence": "公司提供完整教育訓練與員工旅遊",
                    "reason": "公司為員工提供之在職培訓福利，非該職缺所需具備之教育訓練專業規劃技能。",
                },
            ]
        },
    },
    {
        "job_title": "塑膠射出機台操作員",
        "job_desc": "產線機台操作、日常設備保養與維護。工作環境每日需保持整潔清潔。學歷要求研究所畢業尤佳。",
        "candidates": [
            {
                "skill_id": "TW_MFG_001",
                "skill_name_zh": "機台操作",
                "matched_keyword": "機台操作",
            },
            {
                "skill_id": "KS120000000000000004",
                "skill_name_zh": "設備維護",
                "matched_keyword": "維護",
            },
            {
                "skill_id": "KS120000000000000006",
                "skill_name_zh": "清潔",
                "matched_keyword": "清潔",
            },
            {
                "skill_id": "KS120000000000000003",
                "skill_name_zh": "研究",
                "matched_keyword": "研究",
            },
        ],
        "response": {
            "results": [
                {
                    "skill_id": "TW_MFG_001",
                    "skill_name_zh": "機台操作",
                    "matched_keyword": "機台操作",
                    "ac_match": True,
                    "llm_verdict": "KEEP",
                    "confidence": 0.99,
                    "evidence": "產線機台操作、日常設備保養與維護",
                    "reason": "產線技術員主要專業職能要求。",
                },
                {
                    "skill_id": "KS120000000000000004",
                    "skill_name_zh": "設備維護",
                    "matched_keyword": "維護",
                    "ac_match": True,
                    "llm_verdict": "KEEP",
                    "confidence": 0.95,
                    "evidence": "日常設備保養與維護",
                    "reason": "機台日常點檢維護，屬製造現場標準維護技能。",
                },
                {
                    "skill_id": "KS120000000000000006",
                    "skill_name_zh": "清潔",
                    "matched_keyword": "清潔",
                    "ac_match": True,
                    "llm_verdict": "REJECT",
                    "confidence": 0.96,
                    "evidence": "工作環境每日需保持整潔清潔",
                    "reason": "產線一般 5S 環境維護習慣，非專業清潔服務職能。",
                },
                {
                    "skill_id": "KS120000000000000003",
                    "skill_name_zh": "研究",
                    "matched_keyword": "研究",
                    "ac_match": True,
                    "llm_verdict": "REJECT",
                    "confidence": 0.98,
                    "evidence": "學歷要求研究所畢業尤佳",
                    "reason": "『研究所』代表學歷教育機構，並非研發或科學研究專業技能。",
                },
            ]
        },
    },
    {
        "job_title": "Vue 前端工程師",
        "job_desc": "負責企業後台管理系統前端頁面實作，需與後端 Python 工程師密切溝通協調。",
        "candidates": [
            {
                "skill_id": "KS120L96KMYTDJ48NRSH",
                "skill_name_zh": "軟體開發",
                "matched_keyword": "前端頁面實作",
            },
            {
                "skill_id": "KS120000000000000007",
                "skill_name_zh": "Python",
                "matched_keyword": "Python",
            },
            {
                "skill_id": "KS120000000000000005",
                "skill_name_zh": "溝通",
                "matched_keyword": "溝通",
            },
        ],
        "response": {
            "results": [
                {
                    "skill_id": "KS120L96KMYTDJ48NRSH",
                    "skill_name_zh": "軟體開發",
                    "matched_keyword": "前端頁面實作",
                    "ac_match": True,
                    "llm_verdict": "KEEP",
                    "confidence": 0.96,
                    "evidence": "負責企業後台管理系統前端頁面實作",
                    "reason": "前端開發為軟體開發範疇之核心任務。",
                },
                {
                    "skill_id": "KS120000000000000007",
                    "skill_name_zh": "Python",
                    "matched_keyword": "Python",
                    "ac_match": True,
                    "llm_verdict": "REJECT",
                    "confidence": 0.94,
                    "evidence": "需與後端 Python 工程師密切溝通協調",
                    "reason": "Python 出現於跨團隊協作者之職稱中，應徵者本身為前端工程師，非本職位所需技術技能。",
                },
                {
                    "skill_id": "KS120000000000000005",
                    "skill_name_zh": "溝通",
                    "matched_keyword": "溝通",
                    "ac_match": True,
                    "llm_verdict": "KEEP",
                    "confidence": 0.92,
                    "evidence": "需與後端 Python 工程師密切溝通協調",
                    "reason": "跨部門合作溝通協調軟實力。",
                },
            ]
        },
    },
]


def build_verification_prompt(
    job_title: str,
    job_desc: str,
    candidates: List[CandidateSkill],
    tools: Optional[str] = None,
    include_few_shot: bool = True,
) -> List[Dict[str, str]]:
    """組裝呼叫 LLM 的對話訊息列表 (Messages)。
    
    支援 System Prompt、Few-Shot 示範，以及目標職缺的候選項目清單。
    """
    messages: List[Dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]

    if include_few_shot:
        for eg in FEW_SHOT_EXAMPLES:
            user_content = {
                "job_title": eg["job_title"],
                "job_desc": eg["job_desc"],
                "candidates": eg["candidates"],
            }
            messages.append({
                "role": "user",
                "content": f"請驗證以下職缺的候選技能：\n{json.dumps(user_content, ensure_ascii=False, indent=2)}",
            })
            messages.append({
                "role": "assistant",
                "content": json.dumps(eg["response"], ensure_ascii=False, indent=2),
            })

    # 目標待驗證職缺
    candidate_inputs = [
        {
            "skill_id": c.skill_id,
            "skill_name_zh": c.skill_name_zh,
            "matched_keyword": c.matched_keyword,
        }
        for c in candidates
    ]

    target_query = {
        "job_title": job_title,
        "job_desc": job_desc,
        "tools_or_skills_field": tools or "",
        "candidates": candidate_inputs,
    }

    instruction = (
        "請針對上述職缺與候選技能清單進行語境消歧驗證，"
        "嚴格遵循標準回傳包含 results 陣列之 JSON 物件："
    )

    messages.append({
        "role": "user",
        "content": f"{instruction}\n{json.dumps(target_query, ensure_ascii=False, indent=2)}",
    })

    return messages
