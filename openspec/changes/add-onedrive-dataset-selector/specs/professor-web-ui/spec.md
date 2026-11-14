# Capability Spec: `professor-web-ui`（教授操作介面與文案規範）

## Requirement: 移除指定技術文案與 JSON/JSONL 輸入介面
前端介面（`web/index.html`、`web/app.html`、`web/app.js`）MUST 移除「純本地比對，無需 API Key、不呼叫生成式 AI」及其同義宣傳文字，並移除要求教授貼上 JSON／JSONL 陣列的輸入框與說明；底層 API 仍維持 LLM Disabled。

#### Scenario: 檢查首頁渲染文字與互動元件
- **WHEN** 載入 `/`（`web/index.html`）
- **THEN** 頁面中不得出現「純本地比對，無需 API Key、不呼叫生成式 AI」或同義文字
- **AND** 頁面中不得出現 JSON／JSONL 批次文字輸入框或 JSON 格式欄位說明。

## Requirement: 縣市／月份選單與單一分析流程
教授在批次分頁（設為預設或主要入口之一）MUST 能透過動態下拉選單完成「選縣市 → 選月份 → 選抽樣模式 → 點擊『抽取並分析 100 筆職缺』→ 查看結果 → 點擊『下載完整分析報告 (.xlsx)』」，同時保留「單篇手動分析」分頁功能不受影響。

#### Scenario: 切換縣市連動更新月份選單
- **WHEN** 使用者在縣市下拉選單選擇不同縣市
- **THEN** 月份下拉選單立即更新為該縣市於 Manifest 中的可用月份，並顯示該資料集的可用職缺數與抽樣版本提示。

## Requirement: 分析結果直接呈現技能明細與逐筆檢視（UI 回歸修正）
使用者完成分析後，必須在網頁直接看到實際擷取技能名稱與分類，不需要下載 Excel。

#### Scenario: 批次與單篇分析皆直接顯示技能明細與 G1–G10 分布
- **WHEN** 使用者完成單篇職缺分析、示範資料分析、或 100 筆批次／Excel 上傳分析
- **THEN** 網頁必須直接呈現分析總覽、G1–G10 技能分類長條圖與技能明細表（含 `SKILL_NAME_ZH`、`SKILL_ID`、`SKILL_NAME`、`Category`、`Subcategory`、`Skill_group10_code`、`Skill_group10`、`MATCHED_FROM`、匹配證據、`Is_AI_Skill`）
- **AND** 批次模式必須提供可搜尋、依技能數排序、上一筆／下一筆與點擊切換的「職缺清單」，點擊任一職缺即可即時檢視該職缺的技能明細與 G1–G10 分布
- **AND** 零技能職缺必須明確顯示「未擷取到技能」，不得顯示空白區塊。
