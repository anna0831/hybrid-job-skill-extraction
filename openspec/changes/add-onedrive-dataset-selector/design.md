# Design: OneDrive 縣市／月份資料集選單架構設計

## 1. 端到端資料流

```text
OneDrive / 本機清洗後 Excel (cleaned_{縣市}_{YYYYMM}.xlsx)
   │  [本機掃描與脫敏/抽樣腳本 scripts/prepare_web_datasets.py]
   │  - 排除兼職、以 (ID/工作編號 + 資料月份) 去重取樣最多 100 筆
   │  - 計算 source_sha256，不寫入本機絕對路徑或 Token
   ▼
dataset_manifest.json + 對應樣本檔 (web_data/datasets/*.json.gz)
   │  [Startup 唯讀載入]
   ▼
FastAPI 後端 (api/index.py + src/web_adapter.py)
   ├─ GET  /api/datasets          -> 回傳可用縣市、月份、版本與抽樣模式支援狀態
   ├─ POST /api/datasets/sample   -> 依 dataset_id + mode + count 回傳合法樣本（<=100 筆）
   ├─ POST /api/extract           -> 11/11 AC + Rules 擷取（含單篇與批次）
   └─ POST /api/export/xlsx       -> 記憶體產生 4 工作表 .xlsx（含資料集來源追溯欄位）
   │
   ▼
教授專用網頁 (web/index.html + web/app.js)
   └─ 動態縣市選單 -> 動態月份選單 -> 抽樣模式 -> 「抽取並分析 100 筆職缺」 -> 下載 .xlsx
```

---

## 2. OneDrive 資料來源架構比較：Option A vs Option B

| 比較面向 | Option A：預先產生樣本 + `dataset_manifest.json`（第一版預設） | Option B：Microsoft Graph API 即時讀取 OneDrive |
|---|---|---|
| **維護成本** | **低**。本機執行一次掃描腳本即可更新 Manifest 與樣本；後端無需維護 OAuth Token Refresh 與 Graph SDK。 | **高**。需申請 Azure AD App Registration、管理 Client Secret／Refresh Token、處理 Graph API 分頁與錯誤重試。 |
| **資料更新即時性** | **批次同步**。OneDrive 新增月份或修正清洗檔後，需重新執行本機腳本並更新佈署物。 | **即時**。OneDrive 檔案更新後，使用者重新整理網頁即可看到最新月份。 |
| **存取權限與安全** | **可控**。Manifest 僅含索引與安全欄位；若資料未獲公開授權，可只放入脫敏／授權公開樣本，或搭配私有部署存取控制。 | **嚴格但複雜**。需登入驗證與組織權限控管（RBAC），否則公開網頁將成為未授權 OneDrive Proxy。 |
| **Vercel 限制與效能** | **極佳**。壓縮後每縣市月份 100 筆樣本僅數十 KB，無需在 Serverless Function 內讀取 50–100 MB 的原始 `.xlsx`，完全避開 10s/30s Timeout 與記憶體上限。 | **風險高**。單一縣市清洗後 `.xlsx` 達 48–105 MB（實測 `cleaned_臺中市_202609.xlsx` 為 48 MB），在 Vercel 下載並以 `openpyxl` 掃描極易觸發 Timeout 與記憶體溢位。 |
| **技術風險** | 無法支援「從完整數萬筆母體每次真正隨機重抽」，除非後端另存完整去識別母體。 | 依賴 Microsoft 365 帳號權限、Graph API 速率限制及 Vercel Function 執行時間限制。 |

### 第一版決策
- **採用 Option A** 作為第一版預設架構，但嚴格遵守資料安全原則：
  1. **不得將未獲授權公開的完整 OneDrive 原始職缺或完整詞庫直接推上公開 GitHub／無驗證 Vercel**。
  2. 若研究資料尚未獲准公開展示，第一版可先以**脫敏／授權示範樣本**建置 `dataset_manifest.json` 完成驗收，或部署於受存取控制保護的私有預覽環境。
  3. 本階段不實作完整 Microsoft OAuth 流程。

---

## 3. 實機資料欄位檢查結果

實際檢查專案根目錄之 `cleaned_臺中市_202609.xlsx`（48 MB、`Sheet1`、共 60 欄）：
- 識別碼欄位為 **`工作編號`**（非 `ID`），月份欄位為 **`資料月份`**，工作角色欄位為 **`工作角色`**（須比對 `104_single_city_merged_20261111.py` 的 `filter_part_time_jobs` 規則排除 `兼職`）。
- 技能擷取對應欄位：`104職位名稱`、`職位描述`、`工作技能`、`電腦工具`。
- 不同縣市／月份檔案可能有欄位名稱變體（例如 `ID` vs `工作編號`、`職位名稱` vs `104職位名稱`），因此抽樣腳本必須沿用 `normalize_job_fields` 的多別名相容邏輯，不可假設欄位完全一致。

---

## 4. `dataset_manifest.json` 結構規範

Manifest 僅儲存安全索引資訊，**嚴禁出現本機絕對路徑（如 `/Users/anna/...`）、OneDrive Token 或帳號資訊**：

```json
{
  "manifest_version": "1.0.0",
  "generated_at": "2026-11-14T15:15:00+08:00",
  "datasets": [
    {
      "dataset_id": "taichung_202609",
      "city": "臺中市",
      "year_month": "202609",
      "source_filename": "cleaned_臺中市_202609.xlsx",
      "source_sha256": "<sha256>",
      "sample_size": 100,
      "available_job_count": 12450,
      "sample_seed": 42,
      "generated_at": "2026-11-14T15:15:00+08:00",
      "sample_version": "v1_fixed_seed42",
      "access_level": "authorized_demo",
      "sampling_modes_supported": ["fixed"],
      "sample_file": "taichung_202609.json.gz"
    }
  ]
}
```

---

## 5. 固定抽樣 vs 真正隨機抽樣的嚴格區分

- **固定抽樣（Fixed Sampling）**：以 `ID + 資料月份` 去重後排序（或依固定 `sample_seed=42` 抽取最多 100 筆不重複職缺），確保跨程式／詞庫版本可重現與公平比較。
- **隨機抽樣（True Random Sampling）**：每次請求從**完整可用職缺母體**重新不重複抽取 100 筆。
  - **嚴格限制**：在 Option A 下若僅預先存放 100 筆固定樣本，**禁止**將同一批 100 筆重新洗牌後宣稱為「隨機抽樣」。
  - 第一版若後端未持有完整去識別母體，UI 與 `/api/datasets` 必須明確將隨機模式標示為停用（disabled）並說明原因（「第一版採用預先抽樣模式，為確保抽樣代表性與資料安全，僅開放固定抽樣；隨機抽樣需待安全母體後端啟用」）。

---

## 6. 操作流程整合評估

為避免教授依序點擊「抽取樣本」→「開始分析」→「匯出」等技術性按鈕，前端整合為單一主要操作：
1. 教授選好「縣市」、「資料月份」與「抽樣模式」。
2. 點擊單一按鈕 **「抽取並分析 100 筆職缺」**，前端自動依序呼叫 `/api/datasets/sample`（或 `/api/extract` 支援直接帶入 `dataset_id`）完成抽取與 11/11 AC + Rules 分析，並立即呈現摘要、表格與 **「下載完整分析報告 (.xlsx)」** 按鈕。
3. 保留「單篇手動分析」分頁，供教授隨時貼上單筆職缺即時測試。
