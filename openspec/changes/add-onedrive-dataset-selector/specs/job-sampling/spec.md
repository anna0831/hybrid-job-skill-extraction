# Capability Spec: `job-sampling`（100 筆職缺抽樣規則）

## Requirement: 以不重複職缺為單位抽樣
所有抽樣邏輯 MUST 以 `(ID, 資料月份)` 作為唯一職缺識別單位，並排除兼職職缺，不得以 Long Format 技能列進行抽樣，亦不得重複抽取同一 `(ID, 資料月份)` 來湊滿 100 筆。

#### Scenario: 來源母體大於等於 100 筆之固定抽樣
- **WHEN** 呼叫 `POST /api/datasets/sample` 並指定 `mode="fixed"`、`count=100`
- **THEN** 回傳 100 筆不重複 `(ID, 資料月份)` 職缺，且多次呼叫結果完全一致（具可重現性）。

#### Scenario: 來源可用不重複職缺少於 100 筆
- **WHEN** 選定資料集的可用不重複職缺只有 63 筆
- **THEN** `POST /api/datasets/sample` MUST 只回傳 63 筆不重複職缺，並附帶提示訊息說明「實際可用職缺為 63 筆（少於 100 筆），已全數載入」。

#### Scenario: Option A 固定樣本下的隨機模式限制
- **WHEN** 資料集僅預先產生固定 100 筆樣本（`sampling_modes_supported` 不含 `"random"`）而請求 `mode="random"`
- **THEN** 後端 MUST 拒絕以重新排列同一批 100 筆偽裝成隨機抽樣，並回傳 HTTP 400 與明確限制說明。
