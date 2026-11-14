# Vercel Preview Release Report (`hybrid-job-skill-extraction`)

- **報告日期**：2026-11-14
- **Repository Root**：`/Users/anna/Desktop/Job_Description_fetch`
- **目前 Git 分支**：`main`（落後 `origin/main` 2 個 commit；`HEAD = 0b4d8642cce5ebe622c0e8e22fec52ef20b8ab30`）
- **目標分支**：`feature/vercel-professor-demo`（因沙盒禁止寫入 `.git/refs/heads/`，尚未建立，需於本機終端機執行）
- **Vercel Preview URL**：**NOT DEPLOYED**（依 Phase 4／5 安全規範暫停雲端部署，等待使用者核准詞庫受控方案、本機建分支與 Vercel 授權）

---

## 1. Git 安全掃描結果（`PASS`）

- **`git ls-files web_data/`**：空（未追蹤任何 `web_data/` 檔案）。
- **`git check-ignore -v` 實測**：
  - `web_data/lexicon_bundle.json.gz` → 已被 `.gitignore:59` 排除。
  - `web_data/datasets/real_taichung_202609.json.gz` → 已被 `.gitignore:60` 排除。
  - `cleaned_臺中市_202609.xlsx`、`詞庫skill_lexicon_v13_20261111g.xlsx` → 已被 `.gitignore:49` (`*.xlsx`) 排除。
  - `.env` → 已被 `.gitignore:29` 排除；`.pytest_cache/` → 已被 `.gitignore:41` 排除。
  - `web_data/datasets/demo_*.json.gz` → 由 `.gitignore:61` 例外放行；實測 7 份檔案僅含 `data/sample/sample_jobs.jsonl` 之 `DEMO_001`–`DEMO_007` 脫敏示範職缺，無真實 104 原文、無本機路徑、無 Token。

---

## 2. 詞庫部署模式與授權阻礙（`BLOCKED — 等待授權確認`）

- **目前狀態**：`web_data/lexicon_bundle.json.gz`（`1.6 MB`，26,461 筆技能）已受 `.gitignore` 保護，**不會提交至公開 GitHub**。
- **規範限制**：
  - 不可使用公開 GitHub Raw URL 讀取非公開研究詞庫。
  - 不可於前端 JS 存放詞庫、Token 或私有憑證。
  - 不可因缺少正式詞庫而偷偷替換成 `mini_skill_lexicon.csv` 並宣稱是正式研究版。
- **建議受控方案**：將 `web_data/lexicon_bundle.json.gz` 置於受權限控管之私有儲存（如私人 Vercel Blob／私有 S3／Private Build Artifact），於受保護之 Vercel Preview 伺服器端讀取，並搭配 **Vercel Authentication（Deployment Protection）** 限制僅授權帳號可存取。

---

## 3. Dataset Manifest 版本

- **檔案**：[dataset_manifest.json](file:///Users/anna/Desktop/Job_Description_fetch/web_data/datasets/dataset_manifest.json)
- **版本**：`manifest_version: "1.0.0"`、`sample_version: "v1_fixed_seed42"`
- **內容**：7 個 `sanitized_demo` 脫敏示範資料集（臺北市、臺中市、臺南市、高雄市、桃園市、新竹市、彰化縣，`202609`，各 1 筆示範職缺）。

---

## 4. Python Runtime 設定與相依分析（`PASS` 本機最小依賴驗證；`NEEDS VERCEL BUILD OVERRIDE`）

- **ASGI 入口**：[api/index.py](file:///Users/anna/Desktop/Job_Description_fetch/api/index.py) 匯出 `app`（支援 `FastAPI` 與 `Starlette` fallback）。本機 `.venv` 未安裝 `fastapi`（以 `Starlette` 運行），Vercel 部署環境需安裝 `fastapi`。
- **乾淨環境最小 Web 依賴實測（`PASS`）**：
  - 實測封鎖 `pandas`、`numpy`、`nltk`、`streamlit`、`yaml`、`xlsxwriter` 後匯入 `api.index`，原先因 [src/__init__.py](file:///Users/anna/Desktop/Job_Description_fetch/src/__init__.py) 預先 `from src.pipeline import JobSkillPipeline` 而觸發 `pandas` `ModuleNotFoundError`。
  - 已將 `src/__init__.py` 改為 PEP 562 lazy `__getattr__`，修正後實測 `api.index` 可在無 `pandas`/`numpy`/`nltk`/`streamlit` 的乾淨最小環境成功載入，且不影響 CLI/研究腳本。
- **路由與打包設定**：[vercel.json](file:///Users/anna/Desktop/Job_Description_fetch/vercel.json) 已採用官方 `rewrites` 與 `functions.api/index.py`（`memory: 1024`、`maxDuration: 30`、`includeFiles: "web_data/**"`、`excludeFiles` 排除 `tests/**`、`openspec/**`、`docs/**`、`scripts/**`、`104_*.py`、`*.xlsx`、`*.csv`）。
- **`requirements.txt` / `pyproject.toml` 衝突**：Vercel 官方 Python Runtime 會自動安裝根目錄 `requirements.txt` 或 `pyproject.toml`，**不會自動讀取 `requirements-vercel.txt`**。目前 `requirements.txt` 含 `pandas`、`nltk`、`streamlit`、`XlsxWriter`、`pytest` 且缺 `fastapi`。
- **不破壞研究版環境的解法**：保留本機研究版 `requirements.txt` 不變，於 Vercel Project Settings 將 **Install Command** 設為 `pip install -r requirements-vercel.txt`（或於 `feature/vercel-professor-demo` 分支將研究版依賴另存為 `requirements-cli.txt`）。

---

## 5. 驗收測試結果（`PASS` / `FAIL` / `NOT TESTED`）

| 項目 | 狀態 | 實測結果 |
|---|---|---|
| 本機非遺留測試套件 | **PASS** | `tests/`（排除 2 個遺留測試）**98 passed**；`tests/test_web_api.py` **15 passed** |
| 乾淨最小 Web 依賴匯入測試 | **PASS** | 封鎖 `pandas`/`numpy`/`nltk`/`streamlit` 後 `api.index` 正常匯入（已修正 `src/__init__.py`） |
| 臺中市 202609 100 筆 ExactMatch | **PASS** | `100/100` `SKILL_ID` 一致、G1–G10 `0/100` 差異、零技能職缺 `5 == 5` 一致（0.328s） |
| API Health Check（本機 ASGI） | **PASS** | `GET /api/health` 回傳 `ready: true`、`llm_enabled: false` |
| XLSX 下載驗證（本機 ASGI + 100 筆） | **PASS** | 產出 `238.8 KB` `.xlsx`，含 `Skills_Long`、`Group10_Summary`、`Jobs`、`Audit` |
| 雲端 Vercel Preview Build & URL | **NOT TESTED** | 尚未部署（本機無 `vercel` CLI 且待授權確認） |
| 真實 Chrome 瀏覽器 E2E 驗收 | **NOT TESTED** | 本機 Chrome 未開啟遠端除錯（`DevToolsActivePort` ENOENT），無法自動連線測試 |

---

## 6. 尚未解決問題與本機待執行指令

### 6.1 阻礙清單
1. 本機沙盒無法寫入 `.git/refs/heads/`，需於本機 Terminal 建立 `feature/vercel-professor-demo` 並提交。
2. `web_data/lexicon_bundle.json.gz` 的受控雲端存放位置與授權模式尚未拍板（禁止推入公開 GitHub，亦禁止替換為 Mini Lexicon）。
3. Vercel Project 需設定 **Install Command** 使用 `requirements-vercel.txt` 並啟用 **Deployment Protection（Vercel Authentication）**。
4. 真實瀏覽器 12 項 E2E 驗收尚未執行。

### 6.2 本機安全建立分支與檢查指令（請於確認後執行）
```bash
git checkout -b feature/vercel-professor-demo
git add .gitignore vercel.json api/index.py src/web_adapter.py scripts/prepare_web_datasets.py web/ web_data/datasets/dataset_manifest.json web_data/datasets/demo_*.json.gz openspec/ docs/ tests/test_web_api.py requirements-vercel.txt
git status
# 確認 web_data/lexicon_bundle.json.gz 與任何 *.xlsx 皆未出現在 staged 清單後再執行：
git commit -m "feat(web): prepare vercel professor preview release candidate"
```

---

## 7. 最終明確回答

1. **是否已安全建立 Feature Branch？**
   **否**（沙盒禁止寫入 `.git/refs/heads/`，已備妥本機安全建立指令）。
2. **是否已成功部署受保護的 Vercel Preview？**
   **否**（本機無 `vercel` CLI，且依 Phase 4／5 規範，於正式詞庫受控方案與您的明確批准前不得進行雲端部署）。
3. **是否可以讓教授開始試用？**
   **雲端試用：否；本機試用：是**（可於本機執行 `.venv/bin/uvicorn api.index:app --host 127.0.0.1 --port 8000` 由教授在本機瀏覽器試用完整 26,461 技能引擎）。
4. **哪些功能仍只能在本機執行？**
   - 完整 26,461 技能詞庫（`web_data/lexicon_bundle.json.gz`）之無授權雲端部署前分析；
   - 本機全量 OneDrive 縣市／月份原始 `.xlsx` 清洗與 `scripts/prepare_web_datasets.py` 批次抽樣；
   - `104_single_city_merged_20261111.py` 正式研究版全量管線。
