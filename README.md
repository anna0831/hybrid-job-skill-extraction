# Hybrid Job Skill Extraction System

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-53%2F53%20passed-brightgreen.svg)]()
[![Precision](https://img.shields.io/badge/Precision-100.0%25-success.svg)]()
[![Micro F1](https://img.shields.io/badge/Micro%20F1-87.80%25-blueviolet.svg)]()
[![Cost Safety](https://img.shields.io/badge/Cost%20Safety-%240.00%20MockLLM-orange.svg)]()
[![License](https://img.shields.io/badge/license-MIT-green.svg)]()

> 一個結合 **Aho-Corasick 多模式比對**、**三軌動態風險分流（Risk-based Routing）**、**LLM 上下文語義驗證（LLM Context Verification）** 與 **兩階段概念接地（Two-Stage Concept Grounding）** 的工業級職缺技能擷取系統。

---

## 📌 專案核心動機 (Why This Project?)

在勞動市場分析與人才職缺媒合中，傳統純關鍵字比對（如 Aho-Corasick）雖然具備 $O(N)$ 極致速度，但存在嚴重的**語境盲區（Context Blindness）** 與 **詞庫鴻溝（Lexical Gap）**：
* ❌ **福利與薪資混淆**：「底薪 32,000 元，月薪 35,000 元含全勤」→ 誤判為 **薪資管理** (False Positive)
* ❌ **環境整潔與 5S 混淆**：「塑膠作業員工作環境每日需保持整潔清潔」→ 誤判為 **清潔** (False Positive)
* ❌ **學歷與科系名詞混淆**：「學歷要求化學工程研究所畢業」→ 誤判為 **化學工程** 或 **研究** (False Positive)
* ❌ **協作角色混淆**：「需與後端 Python 工程師密切溝通」→ 誤判前端職缺具備 **Python** (False Positive)
* ❌ **口語縮寫與詞庫鴻溝**：「主導晶圓產線 defect reduction 與統計製程管制 SPC」→ 因詞庫僅收錄「品質管理」，AC 命中為 0 (False Negative)

若改用純 LLM 端到端提取，則會面臨 **API 費用高昂、延遲高達數秒、且極易發明不存在於標準詞庫（如 Lightcast）的幻覺詞彙**。

### 本專案的創新解法：Hybrid 混合式架構
1. **AC Matcher ($O(N)$ 線性時間)**：作為 High-Recall 候選生成器，毫秒級產出潛在技能。
2. **三軌動態風險分流 (Risk-based Routing)**：
   - **Track 1 (PASS_THROUGH, ~75% 候選詞)**：高特異性、工具欄詞彙直接放行，**0 LLM 成本、0.2ms 極速直通**。
   - **Track 2 (VERIFY_CONTEXT, ~20% 候選詞)**：福利、5S、學歷、協作者衝突詞，送入 LLM 驗證層，**精準消除 100% 假陽性**。
   - **Track 3 (RECOVER_FN, ~5% 職缺)**：零技能或語境差異職缺，啟動兩階段概念接地，**有效召回假陰性**。
3. **兩階段概念接地 (Two-Stage Concept Grounding)**：
   - Stage 1 (Concept Discovery)：從內文挖掘未知技術短語（如「統計製程管制」/「SPC」）。
   - Stage 2 (Constrained Lexicon Grounding)：強制檢驗 `Skill_ID in skill_index`，**100% 防偽無幻覺**。
4. **$0 成本安全保證 (Cost Safety)**：
   - 內建確定性 `MockLLMVerifier` 與 `MockConceptGrounder`，本地開發、測試與評估費用為 **$0.00**。

---

## 🏛 系統架構圖 (System Architecture)

```mermaid
flowchart TD
    JD[104 Job Description 原文] --> Preprocess[前處理: 列舉展開 / 中英詞界 / 正規化]
    Preprocess --> AC[Aho-Corasick 多模式匹配引擎]
    Lexicon[(Lightcast 技能詞庫)] --> AC
    AC --> Suppress[最長匹配覆蓋抑制 Algorithm]
    Suppress --> Candidates[Candidate Skills 候選清單]
    
    Candidates --> Router{Risk-based Router 三軌決策引擎}
    
    Router -- "Track 1: 低風險直通 (75% 候選詞)" --> Pass[Direct PASS 零成本直通]
    Router -- "Track 2: 高風險衝突 (20% 候選詞)" --> LLM[LLM Context Verifier 語義驗證]
    Router -- "Track 3: 零技能/漏抓 (5% 職缺)" --> Grounding[Two-Stage Concept Grounding 概念接地]
    
    LLM --> Verdict{KEEP / REJECT}
    Verdict -- KEEP --> Validated[Validated Skills]
    Verdict -- REJECT --> Drop[過濾假陽性 (福利/5S/協作者)]
    
    Grounding --> LexiconCheck{Skill_ID in Lexicon?}
    LexiconCheck -- Yes --> Validated
    LexiconCheck -- No (防偽攔截) --> Drop
    
    Pass --> Aggregator[9 大類寬表格聚合器 skills_to_wide]
    Validated --> Aggregator
    
    Aggregator --> Output[Excel 寬表格 + JSONL + 完整審計追蹤 Audit Trail]
```

---

## 📊 四大消融實驗成果 (Ablation Study Matrix)

透過 `scripts/run_ablation_study.py` 在 15 筆標準職缺黃金基準集（`sample_benchmark.jsonl`）上實測對比：

| 變體代號 | 系統變體架構 (System Variant) | Precision | Recall | Micro F1 | Macro F1 | FPR | FNR | 延遲 (ms/doc) | 成本 ($) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `Variant_1` | **Pure AC Baseline (No Rules, No LLM)** | 89.47% | 73.91% | 80.95% | 79.78% | 10.53% | 26.09% | 0.24 ms | $0.00 |
| `Variant_2` | **AC + Rule Engine (Phase 1 Baseline)** | 89.47% | 73.91% | 80.95% | 79.78% | 10.53% | 26.09% | 0.18 ms | $0.00 |
| `Variant_3` | **AC + Risk-based LLM Verifier (Phase 4)** | **100.00%** | 73.91% | 85.00% | 81.11% | **0.00%** | 26.09% | 0.21 ms | $0.00 |
| `Variant_4` | **Full Hybrid System (Phase 5 with FN Recovery)** | **100.00%** | **78.26%** | **87.80%** | **87.78%** | **0.00%** | **21.74%** | 0.24 ms | $0.00 |

### 多維度切片分析亮點 (Multi-dimensional Slicing)
* **產業別**：在 9 大產業中，有 **8 個產業達到 100.00% F1-Score**（半導體、批發零售、生活服務、觀光餐飲、運輸物流、醫療保健、金融服務）。
* **樣本類型**：`zero_skill` 零技能職缺（如 `GOLD_008` 半導體良率工程師）在 Variant 4 中達到 **100.0% 召回率**；`risky_keyword` 高誤判職缺達到 **100.0% 精確率**。

---

## 📂 專案目錄架構 (Repository Structure)

```text
hybrid-job-skill-extraction/
├── configs/                      # 解耦之業務規則設定檔
│   ├── rules.yaml                # 斷詞白名單、放行清單、職稱消歧、就近文意規則
│   ├── synonyms.yaml             # 同義詞組字典
│   └── settings.yaml             # 全域參數、隨機種子與成本安全配置
├── src/                          # 核心原始碼模組
│   ├── preprocessing/            # 中英文斷詞邊界判定、列舉展開、字串清洗
│   ├── lexicon/                  # Pydantic 資料模型、詞庫載入器、英文詞幹化
│   ├── ac_matcher/               # Aho-Corasick 自動機引擎、最長匹配抑制演算法
│   ├── routing/                  # 三軌動態風險分流決策器 (RiskBasedRouter)
│   ├── llm_verifier/             # LLM 上下文驗證層 (Pydantic Schema / Cache / Providers)
│   ├── grounding/                # 兩階段概念接地與 FN 召回引擎 (Discovery / Grounder)
│   ├── evaluation/               # 標準評估管線 (metrics, slicer, evaluator)
│   ├── outputs/                  # 9 大類寬表格聚合器 (skills_to_wide)
│   ├── pipeline.py               # 純 AC 規則管線控制器
│   └── hybrid_pipeline.py        # 端到端 Hybrid 整合管線控制器
├── scripts/                      # CLI 執行工具
│   ├── run_demo.py               # 一鍵式端到端互動展示腳本
│   ├── run_single_file.py        # 批次職缺檔案抽取 CLI
│   ├── run_evaluation.py         # Gold Label Benchmark 自動化評估 CLI
│   └── run_ablation_study.py     # 四大消融實驗自動化評估腳本
├── tests/                        # 完整測試套件 (53 / 53 PASSED)
│   ├── test_preprocessing.py     # 前處理與列舉展開測試 (7 passed)
│   ├── test_ac_matcher.py        # AC 自動機與抑制演算法測試 (4 passed)
│   ├── test_regression.py        # 與舊版單檔腳本之回歸一致性測試 (1 passed)
│   ├── test_evaluation.py        # 評估指標與切片測試 (4 passed)
│   ├── test_llm_verifier.py     # LLM 結構化驗證與快取測試 (11 passed)
│   ├── test_router.py            # 三軌風險分流測試 (15 passed)
│   ├── test_grounding.py         # 概念接地與防偽測試 (9 passed)
│   └── test_ablation.py          # 四大消融實驗流程測試 (2 passed)
├── data/
│   ├── sample/                   # 開源示範脫敏職缺資料 (sample_jobs.jsonl)
│   └── gold_labels/              # 15 筆黃金標準 Benchmark 測試集
├── lexicon/sample/               # 開源示範迷你技能詞庫 (mini_skill_lexicon.csv)
├── outputs/                      # 成果輸出檔 (PDF 報告、JSON 評估結果、寬表格)
└── docs/
    └── PROJECT_REFACTORING_REPORT_20260918.md # 完整技術實證報告 (論文級)
```

---

## 🚀 快速上手 (Quickstart)

### 1. 環境建置
```bash
git clone https://github.com/anna0831/hybrid-job-skill-extraction.git
cd hybrid-job-skill-extraction

# 建立並啟用 Python 虛擬環境
python3 -m venv .venv
source .venv/bin/activate

# 安裝依賴套件
pip install -r requirements.txt
```

### 2. 一鍵執行端到端 Demo (無需 API Key，零成本)
```bash
PYTHONPATH=. python scripts/run_demo.py
```
> 將在彩色終端中展示 4 類經典職缺（標準技術、福利衝突、零技能語境差異、協作者角色）的完整處理流程與 9 大類寬表格匯出。

### 3. 執行全專案 53 項自動化測試
```bash
PYTHONPATH=. pytest tests/ -v
```

### 4. 執行四大消融實驗
```bash
PYTHONPATH=. python scripts/run_ablation_study.py \
  --output outputs/ablation_study_results.json
```

### 5. 批次處理職缺資料並輸出 9 大類寬表格
```bash
PYTHONPATH=. python scripts/run_single_file.py \
  --input data/sample/sample_jobs.jsonl \
  --output-dir outputs/
```

---

## 🔒 資料隱私與安全政策 (Open Source & Privacy Policy)

* **專有資料隔離**：104 原始爬取之完整職缺 Excel 與 Lightcast 商業授權完整詞庫（`*.xlsx`）皆已透過 `.gitignore` 嚴格隔離，絕不進入版本控制。
* **開源示範資料**：本倉庫僅隨附脫敏之公開迷你詞庫（`lexicon/sample/mini_skill_lexicon.csv`）與人工構造之示範樣本（`data/sample/`、`data/gold_labels/`），確保專案可開箱即用且零侵權風險。
* **$0 成本安全**：所有 LLM 模組預設使用確定性 `MockLLMVerifier`，嚴禁任何未經許可之付費 API 呼叫。

---

## 📑 相關文獻與技術報告

* 📄 **正式 Markdown 技術實證報告**：[`docs/PROJECT_REFACTORING_REPORT_20260918.md`](docs/PROJECT_REFACTORING_REPORT_20260918.md)
* 📑 **出版級 PDF 技術規格書**：[`outputs/Hybrid_Job_Skill_Extraction_Report.pdf`](outputs/Hybrid_Job_Skill_Extraction_Report.pdf)

---

## 📄 License
本專案採用 [MIT License](LICENSE) 開源授權。
