# RA Web Testing Guide（兩位研究助理共用測試指南）

本指南確保兩位研究助理（RA）使用**完全相同的 Git Commit、詞庫快照（Lexicon Snapshot）與 Web 擷取介面**進行職缺技能擷取測試與結果比對。

> [!WARNING]
> **切勿直接雙擊開啟 `web/app.html`（`file://` 協定）！**
> `web/app.html` 與 `web/index.html` 必須透過本機 HTTP 伺服器連線後端 `/api/*`（`api/index.py`）才能載入詞庫與執行擷取。直接以 `file://` 開啟瀏覽器會導致 API 請求失敗（CORS / 路徑錯誤）。

---

## 一、兩位 RA 同步環境與啟動（10 步驟）

### Step 1：切換至相同分支並同步最新程式碼
```bash
git checkout feature/vercel-professor-demo
git pull origin feature/vercel-professor-demo
git rev-parse --short HEAD
```
兩位 RA 請確認 `git rev-parse --short HEAD` 輸出的 Commit SHA 一致。

### Step 2：確認正式研究詞庫與資料檔就位
確認專案根目錄或 OneDrive 詞庫路徑存在以下檔案：
- 基底詞庫：`詞庫skill_lexicon_v13_20261111z.xlsx`
- 十大分類：`詞庫skill_lexicon_v13_Chen_grouped_11_2026c.xlsx`

### Step 3：編譯（或確認）Web 唯讀詞庫快照
```bash
.venv/bin/python scripts/prepare_web_lexicon.py
```
確認輸出顯示 `詞庫skill_lexicon_v13_20261111z.xlsx`、`技能總數：26,471`。

### Step 4：設定本機測試 API Token（保護研究資料端點）
```bash
export RESEARCH_API_TOKEN="ra-local-test-token"
```
> 若未設定 `RESEARCH_API_TOKEN`，`/api/datasets/sample`、`/api/extract`、`/api/export/xlsx` 會依 fail-closed 原則回傳 `403`。

### Step 5：啟動本機 FastAPI Web 伺服器
```bash
.venv/bin/uvicorn api.index:app --host 127.0.0.1 --port 8000
```

### Step 6：開啟瀏覽器進入測試頁面
在 Chrome 開啟以下任一網址（兩者介面與功能完全一致）：
- `http://127.0.0.1:8000/app.html`
- `http://127.0.0.1:8000/`

### Step 7：核對頂部 `#healthDetails` 版本資訊列
確認頁面頂部狀態為綠色「系統就緒（11/14 AC + Rules）」，且兩位 RA 看到的以下 7 項欄位完全一致：
1. `Engine Version`（應為 `20261114_web_ac_v1`）
2. `Lexicon Version`（應為 `詞庫skill_lexicon_v13_20261111z.xlsx`）
3. `Lexicon SHA256`（前 12 碼應為 `722cd2832ffa`）
4. `G11c SHA256`（前 12 碼應為 `e35b53bf5ad3`）
5. `Git Commit SHA`
6. `Skill Count`（應為 `26471`）
7. `AI Label Review Status`（應為 `Pending review (315 AI skills flagged)`；若缺少標記欄位則顯示 `Unknown`）

### Step 8：填入 API Token 並執行單篇職缺測試
1. 若介面提示授權，輸入 Step 4 設定的 `RESEARCH_API_TOKEN`。
2. 在「單篇職缺即時分析」貼上測試職缺（例如含否定句「無需 Python、不用會 Excel」、福利「員工健檢」、縮寫「熟悉 GCP 與 CTO 溝通」）。
3. 點擊「開始擷取技能」，直接檢視下方的 **分析總覽（6 KPI）**、**G1–G10 分布長條圖** 與 **技能明細表**（含 `MATCHED_FROM` 與匹配證據）。

### Step 9：執行批次 / 固定抽樣 / XLSX 上傳測試
- **縣市／月份抽樣**：選擇「縣市／月份」後載入 100 筆固定抽樣，使用搜尋框與「上一筆／下一筆」切換逐篇職缺明細；若該職缺零技能，確認顯示「未擷取到技能」。
- **自訂 XLSX 上傳**：上傳最多 100 筆的 `.xlsx`（需含職缺標題與內容欄位），確認批次總覽與逐筆明細正確。

### Step 10：匯出四工作表 Excel 並比對 CLI
點擊「匯出四工作表 Excel（.xlsx）」，確認產出之工作表（`Summary`、`Jobs`、`Skills_Long`、`Group10_Summary`）與 `104_single_city_merged_20261114.py` 產出格式與技能一致。

---

## 二、固定回歸集（Fixed Regression）與滾動探索集（Rolling Discovery）說明

為避免「只看同一批資料導致過擬合」或「每次抽樣不同導致無法追蹤回歸」，建議兩位 RA 同時維護兩類測試集：
1. **固定回歸集（Fixed Regression Set）**：使用固定隨機種子（`seed=42`）抽取之 100 筆標準樣本（如 `臺中市 202609`），每次修改規則或詞庫後必跑，確認已修復的案例沒有退化。
2. **滾動探索集（Rolling Discovery Set）**：自 71 個城市月份（Rolling Validation 範圍）中依不同城市／月份或新月份抽取樣本上傳至 Web UI 進行人工抽檢，找出新的誤命中（FP）與漏抓（FN），再將確認的邊界案例補入固定回歸集。

---

## 三、受保護的線上共用方案（供教授與跨地點 RA 使用）

由於正式完整詞庫與 104 研究職缺原文不得公開暴露於無驗證的網際網路端點，若需線上共用 `app.html`：
1. **Vercel Authentication / Password Protection**：於 Vercel Pro/Team 專案開啟部署保護，僅授權教授與兩位 RA 帳號存取 Preview URL。
2. **Cloudflare Access (Zero Trust)**：若自架於實驗室伺服器或 VM，於前端掛載 Cloudflare Tunnel + Access Email OTP，限研究團隊信箱登入。
3. **API Bearer Token (`RESEARCH_API_TOKEN`)**：於部署環境變數設定強密碼 Token，後端強制驗證 `/api/datasets/sample`、`/api/extract` 與 `/api/export/xlsx`，未授權請求一律回傳 `401` / `403`。

