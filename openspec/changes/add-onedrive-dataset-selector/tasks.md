# Tasks: `add-onedrive-dataset-selector`

## Phase A：OpenSpec 規劃與確認（目前階段）
- [x] A1. 初始化 `openspec/config.yaml` 與 `openspec/changes/add-onedrive-dataset-selector/` 文件結構
- [x] A2. 完成 `proposal.md`、`design.md`、`specs/*`、`tasks.md`
- [x] A3. 等待使用者確認架構與資料授權範圍後，進入 Apply 階段

## Phase B：資料抽樣與 Manifest 建置腳本（Apply 階段）
- [x] B1. 建立 `scripts/prepare_web_datasets.py`，掃描指定本機／OneDrive 清洗後 Excel（支援 `工作編號`/`ID` 別名、排除兼職、以 `ID + 資料月份` 去重）
- [x] B2. 針對授權／脫敏資料產生 `web_data/datasets/dataset_manifest.json` 與對應 `*.json.gz`（固定 seed=42，最多 100 筆不重複職缺）
- [x] B3. 驗證 Manifest 不含本機絕對路徑或 Token，且記錄 `source_filename`、`source_sha256`、`available_job_count`、`sample_version`

## Phase C：後端 API 與 Excel 追溯擴充（Apply 階段）
- [x] C1. 於 `src/web_adapter.py` 新增 Manifest 載入與抽樣讀取函式（含少於 100 筆提示與 Option A 隨機模式防呆），不改動 AC + Rules 判定邏輯
- [x] C2. 於 `src/web_adapter.py` 的 `generate_excel_workbook()` 補充資料集來源追溯欄位（縣市、月份、抽樣版本、程式／詞庫版本），維持 4 工作表結構
- [x] C3. 於 `api/index.py` 新增 `GET /api/datasets` 與 `POST /api/datasets/sample`，並確保 `POST /api/export/xlsx` 支援帶入資料集來源資訊

## Phase D：教授前端介面改造（Apply 階段）
- [x] D1. 從 `web/index.html`、`web/app.html`、`web/app.js` 移除「純本地比對，無需 API Key、不呼叫生成式 AI」與 JSON/JSONL 文字輸入框
- [x] D2. 新增動態「縣市」與「資料月份」下拉選單、抽樣模式選擇（明確標示固定／隨機狀態）、與「抽取並分析 100 筆職缺」單一操作流程
- [x] D3. 保留「單篇手動分析」分頁與「下載完整分析報告 (.xlsx)」按鈕

## Phase E：驗收測試與 Git 管理（Apply 階段）
- [x] E1. 擴充 `tests/test_web_api.py` 覆蓋全部 14 項 Acceptance Criteria（含文案移除、動態選單 API、固定抽樣可重現性、少於 100 筆提示、100 筆 AC+Rules 與 4 工作表 XLSX）
- [x] E2. 確認既有單篇手動分析與 `test_web_api.py` 全部通過，並提供修改前後畫面與驗證報告

## Phase F：UI 回歸修正（恢復技能明細展示與逐筆職缺檢視）
- [x] F1. 診斷並修復 `renderBatchResult()` 隱藏 `#singleResultDetails` 且未渲染 `skills_long` 與 `group10_summary` 之回歸問題
- [x] F2. 恢復單篇與批次皆可見之 6 指標總覽、G1–G10 長條圖、技能標籤與完整技能明細表（含 `Category` / `Subcategory` / `SKILL_ID` / `MATCHED_FROM` / 證據 / `Is_AI_Skill`）
- [x] F3. 新增批次「職缺清單」逐筆檢視（搜尋、依技能數排序、上一筆／下一筆、點擊切換單一職缺或全批彙總、零技能顯示「未擷取到技能」）
- [x] F4. 更新 `specs/professor-web-ui/spec.md` 並通過 `tests/test_web_api.py` 回歸測試
