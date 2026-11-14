# 104 技能擷取系統 — 雙擊離線測試包（RA Offline Testing Package）

> **引擎版本**：`11/14 AC + Rules Pipeline`（`20261114_web_ac_v1_offline_js`）  
> **執行方式**：直接雙擊 `app.html`（`file://`），**無需 Python、FastAPI、Terminal、localhost 或網路連線**。

---

## ⚠️ 重要提醒：必須保留整個資料夾

1. **不可單獨移動 `app.html`**：`app.html` 必須與同層的 `app.js`、`styles.css` 及 `vendor/` 資料夾（內含 `engine_1114.js`、`rules_1114_data.js`、`jieba_lite.js`、`jieba_dict.js`、`xlsx_lite.js`）放在一起。若只複製 `app.html` 到桌面，將無法載入分析引擎。
2. **詞庫安全性（不含於本壓縮包）**：正式詞庫 `lexicon_bundle.json.gz`（26,471 項技能 + G11c）屬受保護研究資料，**不得放入公開 GitHub，也不得內嵌於 HTML**。請向研究室負責人透過授權管道取得 `lexicon_bundle.json.gz`。

---

## 快速操作步驟（5 步驟）

1. **雙擊開啟 `app.html`**：建議使用 **Google Chrome**（網址列應顯示 `file:///.../web-offline/app.html`）。
2. **選取詞庫**：在「Step 1：載入經授權的本機詞庫」點擊選擇檔案，選取本機的 `lexicon_bundle.json.gz`（約 1–2 秒完成本機解壓與建置，狀態燈轉綠並顯示 6 項版本資訊，含 `Skill Count：26471`、`AI Label Review Status：Pending review (315 AI skills flagged)`）。
3. **單篇職缺即時擷取（分頁 A）**：輸入職位名稱、工作內容、工作技能與擅長工具，點擊「執行擷取」，右側即時顯示命中技能（含 `G1–G10`、`Is_AI_Skill`、`MATCHED_FROM`、50 字證據片段）與 Audit 排除原因。
4. **Excel 批次上傳分析（分頁 B）**：上傳 104 職缺 `.xlsx`（自動排除 `工作角色 == "兼職"`、保留 `ID`，上限 100 筆），可用「上一筆 / 下一筆」與搜尋框切換檢視。
5. **下載 4 工作表 Excel**：點擊「匯出 4 工作表 Excel（.xlsx）」，於本機直接下載包含 `Skills_Long`、`Group10_Summary`、`Jobs`、`Audit` 的報告。

