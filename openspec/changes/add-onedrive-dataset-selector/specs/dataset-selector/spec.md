# Capability Spec: `dataset-selector`（動態資料集選取）

## Requirement: 動態載入可用縣市與月份清單
後端 MUST 從 `dataset_manifest.json` 讀取實際存在的資料集索引，並透過 `GET /api/datasets` 提供可用縣市、各縣市對應月份、可用職缺總數、抽樣版本及支援的抽樣模式。

#### Scenario: 正常讀取 Manifest 回傳縣市與月份
- **WHEN** 客戶端呼叫 `GET /api/datasets`
- **THEN** 回傳 HTTP 200，包含依縣市分組的可用 `year_month` 清單、`dataset_id`、`sample_size`、`available_job_count`、`sample_version`、`access_level` 與 `sampling_modes_supported`
- **AND** 不回傳任何本機絕對路徑（如 `/Users/...`）或 OneDrive 憑證。

#### Scenario: 某縣市僅有部分月份資料
- **WHEN** `dataset_manifest.json` 中「臺中市」僅有 `202609`、「臺北市」有 `202608` 與 `202609`
- **THEN** 前端選擇「臺中市」時，月份下拉選單 MUST 只顯示 `202609`
- **AND** 前端 HTML 不得寫死不存在的縣市或月份。

#### Scenario: 尚無可用資料集或未獲授權
- **WHEN** `dataset_manifest.json` 不存在或 `datasets` 為空
- **THEN** `GET /api/datasets` MUST 誠實回傳空清單與明確狀態說明，不得偽造假資料集。
