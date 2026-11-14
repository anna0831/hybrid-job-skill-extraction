# Web App Release Readiness Report (`add-onedrive-dataset-selector`)

- **評估日期**：2026-11-14
- **階段策略**：Phase A（Vercel 教授體驗版優先：脫敏示範資料 + 單篇分析 + `.xlsx` 上傳 + 11/11 AC + Rules + 四工作表下載，停用 LLM）
- **目標分支**：`feature/vercel-professor-demo`（本機沙盒無法寫入 `.git/refs/`，需於本機終端機建立並切換分支）
- **核心引擎版本**：`20261111_web_ac_v1`

---

## 1. 目前是否可以安全地部署至 Vercel Preview？

**答案：尚不可直接部署（NO）。**

雖然後端核心邏輯（100/100 ExactMatch、97 項非遺留測試、四工作表 Excel 匯出）與非示範資料 fail-closed API 驗證皆已通過，但仍有 **3 項實際阻礙** 必須先處理：
1. **Vercel Python 相依套件衝突（部署會失敗或超限）**：Vercel 官方 Python Runtime 預設自動讀取根目錄 `requirements.txt`（不會自動讀取 `requirements-vercel.txt`）。目前 `requirements.txt` 包含 `pandas`、`nltk`、`streamlit`、`XlsxWriter`、`pytest` 且缺少 `fastapi`，直接部署將超出 Vercel 250 MB Serverless Function 上限或導致 `FastAPI` 缺失。
2. **正式完整詞庫部署授權與取得方式未定**：已透過 `.gitignore` 將 `web_data/lexicon_bundle.json.gz`（`1.6 MB`，26,461 筆技能）排除於 Git 追蹤外，避免誤推公開 GitHub；但若要在 Vercel Preview 運行正式 11/11 詞庫，需先確認授權並透過私有儲存／受保護建置環境注入，**不可未經授權將完整詞庫放入公開 GitHub，亦不可改用 Mini Lexicon 冒充正式版**。
3. **實際瀏覽器端到端（E2E）測試尚未完成（`NOT TESTED`）**：尚未於真實瀏覽器完成 9 項人工／自動化驗收。

---

## 2. 測試與驗收總表

| 項目 | 狀態 | 觀察結果 |
|---|---|---|
| 臺中市 202609 100 筆實測 ExactMatch | **PASS** | `100/100` `SKILL_ID` 一致、G1–G10 `0/100` 差異、零技能職缺 `5 == 5` 一致 |
| 4 工作表 Excel (.xlsx) 匯出 | **PASS** | 100 筆實測產出 `238.8 KB`，含 `Skills_Long`、`Group10_Summary`、`Jobs`、`Audit` 與追溯欄位 |
| `tests/test_web_api.py`（Web API 與安全驗證） | **PASS** | **14 passed in 1.82s**（含 `test_protected_dataset_access_control`） |
| `tests/` 全套非遺留測試 | **PASS** | **97 passed in 2.56s**（排除 2 個參照已刪除舊檔之遺留測試） |
| 遺留測試（`test_refactoring_1013.py`、`test_regression.py`） | **FAIL (Collection Error)** | 參照已刪除舊腳本 `104_single_city_1013`、`104_single_file_20260909.py`，與本次 Web App 無關 |
| 實際瀏覽器端到端（E2E）9 項驗收 | **NOT TESTED** | Chrome `DevToolsActivePort` 未開啟且環境未安裝 Playwright／Selenium |

---

## 3. Git 追蹤與詞庫安全狀態（Task 1）

- **`git ls-files` 檢查結果**：目前 Git 僅追蹤開源／脫敏樣本（`data/gold_labels/sample_benchmark.jsonl`、`data/sample/sample_jobs.jsonl`、`lexicon/sample/mini_skill_lexicon.csv`），**未追蹤**任何 `.xlsx`、真實 104 資料或完整詞庫。
- **`.gitignore` 防護強化**：已新增：
  - `web_data/lexicon_bundle.json.gz`（經 `git status --ignored -s web_data/` 實測顯示 `!! web_data/lexicon_bundle.json.gz`）
  - `web_data/datasets/*.json.gz` 與 `!web_data/datasets/demo_*.json.gz`（僅允許已核准的脫敏 `demo_*.json.gz` 可被納入版控，未來任何真實資料集預設皆被忽略）。
- 若日後誤追蹤敏感檔，應使用 `git rm --cached <file>` 安全移出追蹤（不刪除本機檔案、不重寫歷史）。

---

## 4. API 身分驗證狀態（Task 2）

- **`GET /api/datasets`**：僅回傳縣市、月份、抽樣筆數與 `access_level` 等非敏感 Metadata，不含職缺原文。
- **`POST /api/datasets/sample`、`POST /api/extract`（帶 `dataset_id`）、`POST /api/export/xlsx`（帶 `dataset_id`）**：
  - `access_level == "sanitized_demo"`（Phase A 體驗版）：允許免驗證存取，供教授試用脫敏示範資料。
  - `access_level != "sanitized_demo"`（Phase B 正式研究資料）：採 **fail-closed** 保護——未設定環境變數 `RESEARCH_API_TOKEN` 時直接回傳 **403**；已設定時強制檢查 `Authorization: Bearer <token>`（`hmac.compare_digest`），未帶或錯誤回傳 **401**。前端 JS **未硬編碼任何 Token**。
  - 已通過 `test_protected_dataset_access_control` 驗證。
- **上傳防護**：`XlsxUploadRequest.content_base64` 已加入 `max_length=8_000_000` 限制。
- **Phase B 建議方案**：對教授最友善且無須自建帳號系統的方案為 **Vercel Authentication（Deployment Protection）** 或 **Cloudflare Access（Zero Trust Email OTP）** 搭配後端 `RESEARCH_API_TOKEN`／私有資料儲存。

---

## 5. Vercel Python Runtime 相容性（Task 3）

- **`api/index.py`**：當 `fastapi` 存在時使用 `FastAPI`；本機 `.venv` 未安裝 `fastapi`，因此本機測試走 `Starlette` 相容層。
- **`vercel.json`**：已更新為官方推薦之 `rewrites` 語法（取代舊版 `version: 2` + `routes`），並保留 `functions.api/index.py` 設定（`memory: 1024`、`maxDuration: 30`、`includeFiles: "web_data/**"`）。
- **`requirements-vercel.txt` vs `requirements.txt` 衝突**：Vercel 不會自動讀取 `requirements-vercel.txt`，而是讀取根目錄 `requirements.txt` 或 `pyproject.toml`。部署 Vercel Preview 前，請擇一修正：
  1. 在 `feature/vercel-professor-demo` 分支將 `requirements.txt` 替換為 `requirements-vercel.txt` 內容（將本機 CLI／Streamlit 相依移至 `requirements-cli.txt`）；或
  2. 於 Vercel Project Settings 設定 Install Command：`pip install -r requirements-vercel.txt`。
- **`web_data/` 體積**：合計 `1.6 MB`（`lexicon_bundle.json.gz` `1.6 MB` + `datasets/` `36 KB`），遠低於 Vercel 限制，且未掛載於公開靜態路由。

---

## 6. 仍需人工確認與執行清單（Task 4 & Task 5）

### 6.1 本機瀏覽器 9 項人工驗收清單（目前 `NOT TESTED`）
請於本機終端機啟動伺服器後開啟 `http://127.0.0.1:8000` 逐項勾選：
```bash
.venv/bin/uvicorn api.index:app --host 127.0.0.1 --port 8000
```
- [ ] 1. 首頁正常顯示（無「純本地比對，無需 API Key、不呼叫生成式 AI」與 JSON/JSONL 文字框）
- [ ] 2. 縣市與月份下拉選單能正常聯動操作
- [ ] 3. 1 筆示範資料的按鈕文字顯示為「分析 1 筆示範職缺」且標註為脫敏示範資料
- [ ] 4. 點擊分析後能顯示真實 AC + Rules 擷取結果
- [ ] 5. 「單篇手動分析」分頁正常運作
- [ ] 6. 「上傳 Excel (.xlsx)」分頁正常運作
- [ ] 7. 「下載完整分析報告 (.xlsx)」可下載並開啟 4 個工作表（`Skills_Long`、`Group10_Summary`、`Jobs`、`Audit`）
- [ ] 8. 錯誤訊息與載入中狀態正常顯示
- [ ] 9. 桌面版與手機版（例如 `375px` 寬度）版面皆可正常操作

### 6.2 本機建立 `feature/vercel-professor-demo` 分支指令
因沙盒無法寫入 `.git/refs/heads/`，請於本機終端機執行：
```bash
git checkout -b feature/vercel-professor-demo
git add .gitignore vercel.json api/index.py src/web_adapter.py scripts/prepare_web_datasets.py web/ web_data/datasets/ openspec/ docs/WEB_RELEASE_READINESS.md tests/test_web_api.py
git status
# 確認 web_data/lexicon_bundle.json.gz 與 *.xlsx 皆未出現在 staged 清單中再 commit：
git commit -m "chore(web): harden release candidate for professor demo"
```
