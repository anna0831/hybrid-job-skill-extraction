# 104 職缺技能擷取系統 — Vercel 教授展示版遷移盤點報告 (`WEB_MIGRATION_AUDIT`)

> 盤點時間：2026-11-14
> 盤點對象：`/Users/anna/Desktop/Job_Description_fetch`（`hybrid-job-skill-extraction`）
> 原則：**僅使用 11/11 研究版 Aho-Corasick + Rule-based Matching，不啟用 LLM / MockLLM / Embedding**

---

## 1. Git 狀態與本機／GitHub 差異盤點

- **Repository 根目錄**：`/Users/anna/Desktop/Job_Description_fetch`
- **目前分支**：`main`（`0b4d864`），追蹤 `origin/main`（`https://github.com/anna0831/hybrid-job-skill-extraction.git`）
- **遠端比對限制**：沙盒內無法寫入 `.git/FETCH_HEAD` 與連線 GitHub，以下比較以本機既有的 `origin/main`（`d0fb544`）為準。
- **落後遠端 2 commits**：`origin/main` 已合併 PR #1（`feat/sqlite-long-preview`，新增 `src/outputs/sqlite_store.py` 等 16 個檔案），本機尚未拉取，且本機已刪除 `104_single_file_20260930.py`（PR #1 有修改該檔，後續合併須留意 delete/modify 衝突）。
- **已 Commit 未 Push**：0 個 commit。
- **已暫存未 Commit**：無。
- **未暫存變更**：
  - 修改：`requirements.txt`（新增 `XlsxWriter>=3.1.0`）
  - 刪除：`104_run_all_months_20260903.py`、`104_single_city_0919.py`、`104_single_file_20260930.py`、`sample_data_analysis_20260903.py`
- **未追蹤新檔**：`104_single_city_merged_20261111.py`、`104_single_city_merged_20261102.py`、`104_single_city_merged_20261024.py`、`104_single_file_1014.py`、`test_db.py`、`tests/test_refactoring_1013.py`，以及多份 10 月～11/03 詞庫稽核報告與輔助腳本。

---

## 2. 11/11 最新研究檔案檢查結果

| 目標檔案 | 檢查結果 | 路徑／備註 |
|---|---|---|
| `104_single_city_merged_20261111.py` | **已找到** | `/Users/anna/Desktop/Job_Description_fetch/104_single_city_merged_20261111.py`（3,076 行） |
| `詞庫skill_lexicon_v13_20261111g.xlsx` | **未在工作區找到** | `104_single_city_merged_20261111.py` 預設指向 `/Users/anna/Library/CloudStorage/OneDrive-個人/ChenRA/AI_Job_project/詞庫`，位於本工作區之外。 |
| `詞庫skill_lexicon_v13_Chen_grouped_11_2026c.xlsx` | **未在工作區找到** | 同上，位於 OneDrive 外部目錄；工作區內僅有舊版 `1103/詞庫skill_lexicon_v13_Chen_grouped_11_2026.xlsx`、`grouped_lexicon_20261025_synced.xlsx` 與示範檔 `lexicon/sample/mini_skill_lexicon.csv`。 |

> **嚴格聲明**：禁止以 GitHub 舊版 `mini_skill_lexicon.csv` 偽裝為 `20261111g` / `11_2026c` 正式詞庫。我們必須提供獨立的詞庫轉換腳本 `scripts/prepare_web_lexicon.py` 供本機從 OneDrive 正式 `.xlsx` 建置唯讀 JSON bundle，並在 `/api/health` 與 UI 誠實回報實際載入的詞庫版本與狀態。

---

## 3. 可沿用的 11/11 Python 核心功能

來自 `104_single_city_merged_20261111.py`（不依賴 LLM / MockLLM）：

1. **文字正規化與中英前處理**：
   - `_normalize_fullwidth_alnum`（L548）、`_normalize_ascii_hyphen`（L557）
   - `_singularize_word` / `_stem_english_text_with_map`（L583-670，含字元偏移映射與大小寫保護 `_is_lowercased_word_in_english` L421）
   - `expand_enumeration`、`expand_coord`（L672-717，列舉展開與「評估與介入」並列展開）
   - `_get_zh_boundaries`、`_is_word_boundary`（L718-759，jieba 詞界判定與中文 2 字放行白名單 `Allow_Bare_2Char_Keywords`）
2. **詞庫與自動機機制**：
   - `expand_synonyms`（L503，含 `configs/synonyms.yaml` 概念與內建同義詞）
   - `Case_Sensitive_Keywords`（L413, L1053）：純小寫或首字大寫的一般英文單字不可命中全大寫縮寫（如 `ROI`、`SPC`、`PCI`、`GCP`、`GDP`）
   - `Structured_Field_Exact_Tags`（L406, L1044）：僅在 `工作技能` / `電腦工具` 結構化欄位精準比對
   - `Is_AI_Skill`（L2430-2445）：AI 相關技能標記
   - 十大分類與 `G11c` 支援（L890-949）：`Skill_ID`、`Category`、`Subcategory`、`Skill_group10_code`、`Skill_group10`、`Allowed_group_codes`、`Ambiguity_note`
3. **Aho-Corasick 與規則過濾**：
   - `scan_raw_field_matches`（L1808）與 `_suppress_shorter_matches`（L1638，最長匹配覆蓋抑制）
   - `parse_text_sections`（L1313）與 `get_section_for_offset`（L1426）：區分 `duty`、`company_intro`、`benefit`
   - `is_marketing_target_or_domain_modifier`（L1444）：排除行銷／影音／社群服務對象修飾詞
   - `is_context_excluded`（L1572，含 ESG `KS1239Z71LLXDMTGRJ5S`、健檢 `ES92A402F893456D877B`、團險 `BGS423420828D2785973`、PCI 匯流排等）
   - `lacks_required_context`（L1624）：GCP（雲端 vs 臨床試驗）、GDP（藥品運銷）、GO（程式語言）、PCI（PCI-DSS）領域佐證與緊鄰排除
   - `resolve_ambiguous_by_title`（L1694）：無命中時依職稱消歧
   - `review_skill_evidence`（L1750）與 `match_skills_with_evidence_review`（L1970）：彙整證據、保留/待查核/排除決策與同一職缺同一 `Skill_ID` 去重
4. **彙總邏輯**：
   - `build_group10_summary`（L2454）：產出每個職缺 × 十大分類彙總（技能清單、技能數、AI 技能數、技能 ID 清單）。

---

## 4. 需要抽離／隔離的 CLI 與環境邏輯

`104_single_city_merged_20261111.py` 目前把核心邏輯與 CLI 強耦合，Web Adapter（`src/web_adapter.py`）必須將以下部分完全抽離：

1. **啟動期副作用（Top-level Side Effects）**：
   - L98-106：缺套件檢查並呼叫 `sys.exit(1)`。
   - L116-117：`nltk.download("wordnet")`、`nltk.download("omw-1.4")` 於 import 時執行，在 Vercel read-only 環境與 Cold Start 會造成失敗或大幅延遲（Web Adapter 應改用可離線運作的輕量英文字形還原 `_singularize_word`，或預設指向 `/tmp/nltk_data` 且不強制聯網下載）。
2. **本機檔案系統與互動輸入**：
   - L130-162：`_ONEDRIVE_PROJECT_DIR`、`_WHC2_DATA_ROOT`、`104_paths_config.json`。
   - L186-297：`_ask_path()`、`_prompt_for_input_file()`、`_resolve_run_paths()` 內的 `input()` 互動流程。
3. **大型批次 I/O 與外部腳本呼叫**：
   - `main()` 內的 `pd.read_excel` 整份職缺、Parquet 寫出、`test_db.py`、`keyword_gap_miner.py` 子程序呼叫。
4. **每次請求重建自動機問題**：
   - 原本在 CLI 啟動時讀取 `.xlsx` 建立 `ahocorasick.Automaton`。Web 版必須改為：
     1. Build time 由 `scripts/prepare_web_lexicon.py` 將 `.xlsx` 預先轉成唯讀 `JSON`（含全部 `Skill_ID`、keywords、規則欄位、十大分類、AI 標記與版本 SHA-256）。
     2. FastAPI / Serverless 啟動時以模組級單例快取（Singleton Cache）載入自動機，不在每次 Request 重建。

---

## 5. Vercel 部署限制與技術風險評估

| 面向 | 風險評估 | 緩解策略 / 替代架構 |
|---|---|---|
| **Python Runtime & Build Dependencies** | `pyahocorasick` 含 C 擴充；`jieba`、`openpyxl` 為純 Python。Vercel Python runtime 支援 `manylinux` wheels。 | 使用 `requirements-vercel.txt` 精簡依賴：**移除** `pandas`、`pyarrow`、`numpy`、`nltk`、`streamlit`、`torch` 等重型套件，改用純 Python + `pyahocorasick` + `jieba` + `openpyxl`（寫 `.xlsx`）。 |
| **Function Bundle Size（250 MB unzipped 上限）** | 若納入 `pandas` + `pyarrow` + `numpy` + `nltk`，極易逼近或超過 250 MB。 | 抽離 `src/web_adapter.py` 後**完全不依賴 `pandas`/`numpy`/`pyarrow`/`nltk`**，可將 Python 依賴壓縮至 ~40–60 MB。 |
| **Cold Start 與記憶體** | `jieba` 字典載入約 0.3–0.5s；完整詞庫 JSON 載入並建立 AC 自動機約需 0.5–1.5s、記憶體 ~150–300 MB。 | 預先將 `.xlsx` 轉為精簡唯讀 `.json.gz`，並以全域單例快取自動機；若詞庫過大超過 Hobby 方案記憶體，改採 **Vercel 靜態前端 + 獨立 Python API（Render / Railway / Cloud Run）**。 |
| **唯讀檔案系統與 `jieba.cache`** | Vercel `/var/task` 為唯讀，只有 `/tmp` 可寫；`jieba` 預設可能嘗試在系統暫存寫入 `jieba.cache`。 | 確保 `TMPDIR` / `jieba.dt.tmp_dir = "/tmp"`，且不將使用者資料或 Excel 暫存寫入專案目錄。 |
| **Timeout（Hobby 10s / Pro 60s）** | 單篇分析 < 50ms；100 筆批次純 AC + Rules 約 0.5–2s（Cold Start 除外）。 | 加入輸入上限（單次最多 100 筆、單篇字數上限）與超時保護；Excel 於記憶體 `BytesIO` 產生。 |
| **Vercel Response Size（4.5 MB 上限）** | 100 筆職缺完整原文 + `Skills_Long` + `Audit` 轉成 `.xlsx`（壓縮 ZIP 格式）通常約 100 KB–800 KB，遠低於 4.5 MB；但極端長文仍可能接近上限。 | 若單次回應超過 4 MB，建議改由前端分批分析後在瀏覽器端組裝或改採獨立 Python API（Cloud Run / Railway）。 |
| **中文檔名與編碼** | HTTP `Content-Disposition` 需支援 RFC 5987 或 ASCII 安全檔名；Excel 內部文字須防公式注入與強制 `Skill_ID`/`Job_ID`/`資料月份` 為文字格式 `@`。 | 固定檔名 `104_skill_extraction_YYYYMMDD_HHMMSS.xlsx`（ASCII 安全），Excel cell 明確設定 `number_format = "@"`。 |
| **部署費用風險** | 本階段完全停用 LLM / Embedding，無任何 API token 費用；Vercel Hobby 免費額度內可執行展示，但需防範惡意大流量／超大 payload。 | API 層加入欄位長度上限、批次筆數上限（100 筆）與速率/體積保護，Log 不印出職缺原文。 |
