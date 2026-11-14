# Capability Spec: `excel-report`（4 工作表 XLSX 報告相容性）

## Requirement: 維持四工作表結構並補充資料來源追溯資訊
`POST /api/export/xlsx` 產出之 `104_skill_extraction_YYYYMMDD_HHMMSS.xlsx` MUST 維持且僅包含 4 個工作表：`Skills_Long`、`Group10_Summary`、`Jobs`、`Audit`，並維持 11/11 AC + Rules 結果、零技能職缺保留及文字格式 `@`。同時須於工作表記錄資料集來源資訊（縣市、月份、抽樣版本、程式版本、詞庫版本）。

#### Scenario: 由縣市／月份抽樣結果匯出 XLSX
- **WHEN** 教授針對選定的縣市與月份完成分析並點擊「下載完整分析報告 (.xlsx)」
- **THEN** 下載真實 `.xlsx` 檔案，內含 `Skills_Long`、`Group10_Summary`、`Jobs`、`Audit` 4 個工作表
- **AND** `Jobs` 保留全部抽樣職缺（含零技能職缺），`ID`、`資料月份`、`SKILL_ID` 均以文字格式 `@` 保存
- **AND** 紀錄中可追溯該次分析的 `縣市`、`月份`、`抽樣版本`、`程式版本` 與 `詞庫版本`。
