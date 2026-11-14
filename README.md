# Hybrid Job Skill Extraction System

SQLite long format 查核：新增分批轉檔、完整原始職缺補入、每頁 100 筆 preview，
以及餐飲／補教／醫療人工查核候選匯出。操作指令、統計範圍與測試見
[SQLite 使用文件](docs/sqlite_usage.md)。正式 DB 與資料留在本機；本機既有 test_db.py 不需覆寫。

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Engine](https://img.shields.io/badge/engine-11%2F14%20AC%20%2B%20Rules%20(No%20LLM)-blue.svg)]()
[![Lexicon](https://img.shields.io/badge/lexicon-26%2C471%20skills%20(1111z)-teal.svg)]()
[![Web ExactMatch](https://img.shields.io/badge/Web%2FCLI%20ExactMatch-100%2F100-success.svg)]()
[![License](https://img.shields.io/badge/license-MIT-green.svg)]()

> 本專案提供 104 台灣職缺資料的技能擷取研究流程與教授／研究助理共用 Web 測試平台。**現行正式研究與 Web 擷取引擎採用純 Aho-Corasick + 語境／否定句證據審查（無 LLM）**，並完整保留早期 **Hybrid + LLM** 實驗架構作為歷史基準對照。

---

## 一、三大流程架構總覽（2026/11/14 狀態）

| 流程 | 定位 | 核心技術 | 詞庫與分類 | 狀態 |
| :--- | :--- | :--- | :--- | :--- |
| **1. Current AC + Rules Pipeline**<br>(`104_single_city_merged_20261114.py` Candidate；Stable Baseline 為 `20261111.py`) | **現行正式研究主線** | Aho-Corasick + 否定句排除（`無需`/`不需`/`不用`/`不必`/`免`）+ 前後 50 字語境排除 + 150–300 字縮寫消歧 + `Case_Sensitive_Keywords` + `Structured_Field_Exact_Tags`（**無 LLM**） | Candidate：`詞庫skill_lexicon_v13_20261111z.xlsx`（**26,471** 技能）+ `詞庫skill_lexicon_v13_Chen_grouped_11_2026c.xlsx`（26,626 列，SHA256 `31f5e3e2beeb...`）<br>Stable Baseline：`1111g`（26,461 技能） | ✅ **已整合（11/14 Candidate）** |
| **2. Professor / RA Web Demo**<br>(`api/index.py` + `src/web_adapter.py` + `web/app.html`) | **教授與兩位 RA 共用測試介面** | 與 CLI 共用 `src/ac_rules_1114.py` 規則模組，支援單篇即時分析、縣市／月份 100 筆固定抽樣、自訂 XLSX 上傳（上限 100 筆）、四工作表 `.xlsx` 匯出 | 唯讀壓縮快照 `web_data/lexicon_bundle.json.gz`（26,471 技能，315 AI 技能） | ✅ **100/100 ExactMatch 驗證通過** |
| **3. Legacy Experimental Hybrid + LLM**<br>(`src/pipeline.py`, `src/llm_verifier.py`) | **早期實驗架構（歷史對照）** | AC Matcher + 三軌風險分流 + LLM 上下文驗證 + 兩階段概念接地 | 歷史評估基準（53/53 舊版測試、歷史評估指標：Precision 100.0% / Micro F1 87.80% / MockLLM $0.00） | 📦 **僅作歷史保留，非現行研究主力** |

> [!NOTE]
> 詳細的 11/11 Baseline 與 11/14 Candidate 檔案 SHA256、規則差異與已知差距，請見 [RESEARCH_VERSION_CHANGELOG.md](docs/RESEARCH_VERSION_CHANGELOG.md)。

---

## 二、2026/11/14 研究引擎與詞庫更新重點

1. **詞庫擴充（26,461 → 26,471 技能）**：
   - 新增 10 項技能：`TW_AI_001`（Midjourney）、`TW_AI_002`（Runway AI影片生成）、`TW_AI_003`（Perplexity）、`TW_JIBAO_001`（集保作業）、`TW_SEMI_020`（CPLD複雜可程式邏輯元件）、`TW_SW_005`（HTTP協定）、`TW_SW_006`（WPS Office）、`TW_SW_007`（Corel Painter）、`TW_SW_008`（CoolDraw）、`TW_SW_009`（dBase）。
   - 清理約 2,186 項關鍵字異動，並保留 `Case_Sensitive_Keywords` 與 `Structured_Field_Exact_Tags` 精確比對規則。
2. **否定句排除（`_NEGATION_RE`）**：於 `職位描述` 排除「無需 / 不需 / 不用 / 不必 / 免」前綴的技能命中。
3. **福利、公司介紹與招募文案過濾**：排除員工福利、健康檢查、公司介紹段落中的非技能誤命中。
4. **縮寫與一詞多義消歧**：強化 `GCP`、`GDP`、`PCI`、`Go`、`CTO`、IC 設計 `IPs`、門市 `銷售管理` 等 150–300 字領域佐證與 50 字語境排除。
5. **G11c 十大分類與 AI 候選標記狀態**：
   - 已同步 OneDrive 最新版 `詞庫skill_lexicon_v13_Chen_grouped_11_2026c.xlsx`（2026/11/13，SHA256 `31f5e3e2beeb...`，26,626 列），包含新增 10 項技能分類、`n8n` 改列 G8，以及 8 項 TW-ONET 誤分類修正（含建築營造 `Building And Construction` → G10、手工靈巧度 `Manual Dexterity` → G3）。
   - **AI 技能人工覆核狀態**：`Is_AI_Skill = 'Y'` 由 11/11 的 312 項增至 11/14 的 315 項（新增 `TW_AI_001` Midjourney、`TW_AI_002` Runway AI影片生成、`TW_AI_003` Perplexity；0 項取消），屬**尚待團隊人工確認之候選清單（不可當作已驗證 Gold Label）**，Web `/api/health` 依實際詞庫動態標示 `Pending review (315 AI skills flagged)`。

---

## 三、兩位研究助理（RA）共用測試介面（三種使用模式）

### 模式一：雙擊離線單機版（`web-offline/app.html`，免 Python / 免 Terminal）

適合研究助理直接在本機 Chrome **雙擊 `web-offline/app.html`（`file://` 協定）**執行完整 11/14 AC + Rules 技能擷取（100/100 ExactMatch 驗證通過）：
- 無須啟動 FastAPI / Uvicorn、無須安裝 Python、無須 `localhost` 或網路連線。
- 基於安全隔離設計，正式詞庫不內嵌於 HTML；開啟頁面後手動選取本機 `web_data/lexicon_bundle.json.gz` 即可於瀏覽器記憶體完成解壓、單筆分析、Excel 批次上傳（上限 100 筆、自動排除兼職）與 4 工作表 `.xlsx` 匯出（`Skills_Long`、`Group10_Summary`、`Jobs`、`Audit`）。
- 操作教學見 **[OFFLINE_RA_TESTING_GUIDE.md](docs/OFFLINE_RA_TESTING_GUIDE.md)**；技術可行性與 CLI 等價驗證見 **[OFFLINE_TECHNICAL_FEASIBILITY.md](docs/OFFLINE_TECHNICAL_FEASIBILITY.md)**。

### 模式二：本機 FastAPI 研究測試版（`web/app.html`）

> [!IMPORTANT]
> **請勿直接雙擊開啟 `web/app.html`（`file://` 協定）**，必須啟動本機 FastAPI 伺服器後以 `http://127.0.0.1:8000/app.html`（或 `http://127.0.0.1:8000/`）開啟。

```bash
# 1. 編譯最新 11/14 Web 詞庫快照（26,471 技能）
.venv/bin/python scripts/prepare_web_lexicon.py

# 2. 設定受保護端點 Token
export RESEARCH_API_TOKEN="your-local-test-token"

# 3. 啟動本機 Web API 伺服器
.venv/bin/uvicorn api.index:app --host 127.0.0.1 --port 8000
```

完整 10 步驟同步流程、Fixed Regression（`seed=42` 固定回歸集）vs. Rolling Discovery（71 城市月份滾動探索集）測試規範，請參閱 **[RA_WEB_TESTING_GUIDE.md](docs/RA_WEB_TESTING_GUIDE.md)**。

### 模式三：受保護的 Vercel Preview（尚未部署）

- 正式 26,471 項技能詞庫尚未取得雲端部署授權，目前**尚未部署**至 Vercel；公開 Repo 亦嚴格排除 `web_data/lexicon_bundle.json.gz` 與正式研究詞庫。

---

## 四、輸出格式與驗證結果

- **CLI 輸出**：Long-format 明細、Wide-format 職缺技能表、Group10 十大分類統計、Audit 排除紀錄（`.jsonl`）。
- **Web 匯出（4-Sheet `.xlsx`）**：`Summary`、`Jobs`、`Skills_Long`、`Group10_Summary`。
- **11/14 Web / CLI 一致性驗證（臺中市 202609，`seed=42` 100 筆兼職排除後樣本）**：
  - `Skill_ID ExactMatch`：**100 / 100**
  - 技能總列數：CLI **884** vs. Web **884**
  - 零技能職缺數：CLI **4** vs. Web **4**
  - G1–G10 分類差異：**0**
  - AI 技能旗標差異：**0**

---

## 五、資料與 API 安全保護

- **公開 GitHub 資料隔離**：`.gitignore` 排除正式 Excel 詞庫、104 原始與清洗後職缺資料、`web_data/lexicon_bundle.json.gz`，以及未獲授權的研究抽樣資料，避免敏感研究資料被提交至公開 Repository。
- **API 存取驗證**：`/api/datasets/sample`、`/api/extract` 與 `/api/export/xlsx` 對非 `sanitized_demo` 資料集執行 `RESEARCH_API_TOKEN` Bearer 驗證；未設定 Token 回傳 `403`，缺少或錯誤 Token 回傳 `401`。脫敏示範資料不適用這項資料集 Token 驗證。
- **資料集資訊**：`GET /api/datasets` 僅回傳經允許顯示的資料集 Metadata，不公開未授權職缺原文。
- **前端安全**：不得將 API Token、私人研究詞庫或儲存空間憑證硬編碼於 JavaScript。
- **部署限制**：正式 26,471 項技能詞庫尚未取得雲端部署授權，因此目前僅支援經授權的本機研究測試；Vercel Preview 尚未正式驗收。

---

## 六、License

本專案採用 [MIT License](LICENSE) 開源授權。
