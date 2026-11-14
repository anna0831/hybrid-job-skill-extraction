# Proposal: 新增 OneDrive 縣市／月份職缺選單 (`add-onedrive-dataset-selector`)

## 1. 背景與問題定義

目前 `hybrid-job-skill-extraction` 的 Vercel 教授展示版已具備 11/11 AC + Rules 引擎、26,461 筆技能詞庫、G11c 十大分類與 4 工作表 Excel (`.xlsx`) 匯出功能；然而在批次操作介面中，使用者仍需手動貼上 `JSON 陣列或 JSONL`（含 `job_title`、`job_description`、`job_skills`、`computer_tools` 等技術欄位），對沒有技術背景的教授非常不直觀。

同時，首頁與介面中仍殘留「純本地比對，無需 API Key、不呼叫生成式 AI」等技術宣傳文案，與研究展示定位不符，需予以移除（底層仍維持 LLM Disabled）。

## 2. 變更目標

1. **移除技術性操作與指定文案**：
   - 從 `web/index.html`、`web/app.html`、`web/app.js` 移除「純本地比對，無需 API Key、不呼叫生成式 AI」及其同義宣傳文字。
   - 從教授操作介面移除 JSON / JSONL 文字輸入區與技術說明（內部 API 仍保留 JSON 交換格式）。
2. **改為「縣市 × 月份」動態選單流程**：
   - 教授開啟網站 → 選擇縣市 → 選擇資料月份 → 選擇抽樣模式（預設固定抽樣；隨機模式依後端母體存取能力決定啟用或清楚標示限制）→ 點擊「抽取並分析 100 筆職缺」→ 查看結果 → 下載「完整分析報告 (.xlsx)」。
   - 縣市與月份清單完全由 `dataset_manifest.json` 動態產生，禁止寫死於 HTML。
3. **建立可追溯且安全的資料抽樣管線**：
   - 盤點 OneDrive / 本機清洗後 Excel（如 `cleaned_臺中市_202609.xlsx`），以 `ID (工作編號) + 資料月份` 為不重複職缺抽樣單位。
   - 在 `Skills_Long`、`Group10_Summary`、`Jobs`、`Audit` 匯出中補充資料來源追溯資訊（縣市、月份、抽樣版本、程式／詞庫版本），並維持單篇手動分析與既有 `.xlsx` 匯出功能不受影響。

## 3. 非目標（Out of Scope）

- 不啟用任何 LLM、MockLLM 或 Embedding。
- 不修改 11/11 正式 AC + Rules 技能判定邏輯。
- 不在本階段實作完整 Microsoft OAuth 2.0 登入流程（除非權限審查確認為唯一可行方案）。
- 不將未獲授權公開的 OneDrive 原始職缺檔上傳至公開 GitHub 或無存取控制的 Vercel。
