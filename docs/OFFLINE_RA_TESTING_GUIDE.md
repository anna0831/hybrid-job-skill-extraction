# 研究助理（RA）雙擊離線版 `web-offline/app.html` 測試指南

本指南說明如何在**不安裝 Python、不開啟 Terminal、不啟動 localhost、不連網**的情況下，直接雙擊開啟 `web-offline/app.html` 進行 104 職缺技能擷取測試。

---

## 一、事前準備（取得兩樣檔案）

請向專案負責人取得以下檔案（**兩者皆不可上傳至公開 GitHub**）：

1. **`web-offline/` 資料夾**（完整複製整個資料夾，內含 `app.html`、`app.js`、`styles.css` 與 `vendor/` 子資料夾）
2. **詞庫壓縮檔 `lexicon_bundle.json.gz`**（由 `v13_20261111z` 與 `G11c` 編譯之唯讀快照，26,471 項技能）

---

## 二、操作步驟（5 步驟完成測試）

### 步驟 1：雙擊開啟 `app.html`
- 開啟 Finder，進入 `web-offline/` 資料夾。
- 直接**雙擊 `app.html`**（使用 Google Chrome 開啟）。
- 確認網址列為 `file:///.../web-offline/app.html`，頁面頂部顯示「離線單機版（file://）」。

### 步驟 2：載入本機詞庫 `lexicon_bundle.json.gz`
- 在頁面「1. 載入詞庫快照」區塊點擊選擇檔案，選取本機的 `lexicon_bundle.json.gz`。
- 約 1–2 秒後，右上角狀態燈會轉為綠燈，並於頂部版本列顯示 6 項資訊：
  - `Engine Version`：`20261114_web_ac_v1_offline_js`
  - `Lexicon Version`：`詞庫skill_lexicon_v13_20261111z.xlsx`
  - `Lexicon SHA256`：`722cd2832ffa...`
  - `G11c SHA256`：`31f5e3e2beeb...`
  - `Skill Count`：`26471`
  - `AI Label Review Status`：`Pending review (315 AI skills flagged)`

### 步驟 3：單筆職缺即時測試（Mode A）
- 在「單筆職缺即時擷取」輸入：
  - **職位名稱**（例如：`Cloud Engineer`）
  - **工作內容 / 職位描述**（例如：`熟悉 Google Cloud Platform (GCP) 與 Kubernetes，無需 Java`）
  - **工作技能**（選填）
  - **擅長工具 / 電腦工具**（選填，例如：`Python、Git`）
- 點擊「執行擷取」，即可於右側查看：
  - 命中技能明細：`Skill_Name_ZH`、`SKILL_ID`、`Category / Subcategory`、`G1–G10`、`Is_AI_Skill`、`MATCHED_FROM` 與 50 字前後文證據片段（`EVIDENCE_SNIPPET`）。
  - **Audit 審查紀錄**：可檢視哪些詞因「否定句排除」或「上下文規則排除」而被過濾，以及保留原因。

### 步驟 4：批次 Excel 上傳與檢視（Mode B）
- 點擊「批次 Excel 職缺上傳（.xlsx）」，選取欲測試的 104 職缺 `.xlsx` 檔案。
- 系統會自動：
  - 保留原始 `ID` 與欄位
  - 自動排除 `工作角色 == "兼職"` 的列
  - 上限處理前 **100 筆**有效職缺
- 擷取完成後，可使用**上一筆 / 下一筆**按鈕或**關鍵字 / Job ID 搜尋**切換檢視每筆職缺的命中技能與 Audit 排除原因。

### 步驟 5：匯出 4 工作表 `.xlsx` 報告
- 點擊「匯出 4 工作表 Excel（.xlsx）」，瀏覽器將直接在本機產生並下載 `offline_skill_extraction_YYYY-MM-DD.xlsx`，內含 4 個工作表：
  1. `Skills_Long`（每筆職缺命中技能長表）
  2. `Group10_Summary`（各職缺 G1–G10 分類統計）
  3. `Jobs`（各職缺技能總數與 AI 技能數）
  4. `Audit`（排除與保留證據審查明細）

---

## 三、常見問題排解

- **看不到技能命中或按鈕無法點擊？**  
  請先確認已完成「步驟 2」載入 `lexicon_bundle.json.gz`，且頂部版本列已顯示 `Skill Count：26471`。
- **移動 `app.html` 到桌面後無法執行？**  
  `app.html` 需搭配同資料夾內的 `app.js`、`styles.css` 與 `vendor/` 使用，請複製整個 `web-offline/` 資料夾，不要只單獨複製 `app.html`。
- **AI 技能標記說明**：`Is_AI_Skill = Y`（共 315 項）為研究候選標記，目前狀態為 `Pending review`，尚未完成團隊人工最終審核，請勿直接當作已驗證 Gold Label。

