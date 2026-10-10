# SQLite 轉檔、Long preview 與人工查核

本工具新增在 `scripts/parquet_to_sqlite.py`；不會覆蓋本機既有 `test_db.py`。
完整 DB、Parquet、商業詞庫及人工查核資料留在本機，不提交公開 GitHub。

## 安裝與測試

在 repository 根目錄執行：

```bash
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest tests/test_sqlite_export.py tests/test_sqlite_review.py -q
```

## 將既有 long Parquet 轉成新的 DB

```bash
.venv/bin/python scripts/parquet_to_sqlite.py \
  --input "AC 後檔案/skills_臺中市_202609_long.parquet" \
  --db skills_taichung_202609_v2.db
```

目標已存在時預設拒絕；確定要取代才加 `--overwrite`。Parquet 使用
`ParquetFile.iter_batches()`（預設 5,000 列），CSV/JSONL 逐列、XLSX 以 read-only
模式讀取第一張工作表。CSV 預期 UTF-8/UTF-8 BOM，無法保留 CSV 已失去的 NULL 語意。
ID/代碼的前導零只能保留來源仍有的字元；已轉成數值的前導零無法重建。
NULL 與空字串分開保存，非法布林值報錯。所有來源 long 列，包括技能全空及重複列，
都寫入 `skill_records`，不得以「空技能」為由略過。

資料表：

| 表／檢視 | 意義 |
| --- | --- |
| `jobs` | `(ID, 資料月份)` 一筆職缺快照；原始九欄 |
| `skill_records` | 一列來源 long 明細；不代表一個不重複技能 |
| `v_skill_long` | `jobs LEFT JOIN skill_records`，前兩欄 category/subcategory；原始分類與十大分類各自保留 |
| `raw_job_sources` | 原始職缺來源列及全部原始欄位 JSON，包含來源提供的產業資訊 |
| `import_runs` | 本工具實際執行的輸入模式、來源、列數及時間 |

新增工具以 `source_payload` 保留完整來源列（包含未映射欄位），因此新 DB 的
磁碟大小可能比原本只保留固定欄位的 DB 大。記憶體不會因此載入完整資料。
來源位置 `source_row` 從 1 起算，表示檔案的資料列順序，不是 Excel 工作表列號。

## 用現有 DB 啟動每頁 100 筆 preview

```bash
SKILL_DB_PATH="$PWD/skills_taichung_202609.db" \
  .venv/bin/python -m streamlit run sqlite_app.py
```

也可以執行 `app.py`，在側邊欄選「SQLite Long 查核」。獨立的 `sqlite_app.py`
不初始化詞庫與擷取 pipeline。preview 相容報告所述 jobs/skill_records/v_skill_long
欄位；若實際 schema 缺少必要欄位會明確報錯，請先檢查 PRAGMA table_info。

操作：套用篩選 → 上／下一頁 → 選擇本頁職缺 → 點「載入職缺原文」。
SQL 每次最多讀取 101 筆（100 筆＋是否有下一頁的 lookahead），不 SELECT 全表後切頁。
分頁使用 `(ID, 資料月份, COALESCE(record_id,0))`，包括沒有技能明細的職缺。
原文不包含在分頁查詢中，只有按下按鈕才查 jobs；CSV 下載限定當頁。
查詢連線為唯讀、參數化 SQL；快取設 TTL 和數量上限，並以 DB/WAL 版本區分。
職稱搜尋只是找案例，不能視為產業判定。不要將未加存取控制的正式資料庫接上公開展示站。
雲端部署的 Streamlit 無法直接讀你 Mac 的檔案；完整資料查核先在本機執行。

## 補入完整原始職缺（不重跑擷取、不製造技能）

先關閉資料庫檢視器與寫入程式，備份現有 DB。把下列來源替換成實際檔案：

```bash
.venv/bin/python scripts/parquet_to_sqlite.py \
  --input "/完整路徑/原始職缺.xlsx" \
  --db skills_taichung_202609.db \
  --mode raw-jobs --month 202609
```

也支援原始 Parquet、UTF-8 CSV、JSONL。`--month` 只補來源缺少的月份，不改寫已有月份。
CSV 或 Parquet 僅有擷取成果，不等於完整原始職缺。XLSX 若有多張來源工作表，需先明確
選取／匯出所需工作表，工具不自動合併。

raw-jobs 模式先 backup 現有 DB 到暫存檔，核對後原子替換；衝突時目標不變。
既有職缺的非 NULL 原文衝突會報錯，不默默改寫。重複匯入會保留原始來源列供查核，
但 jobs 的職缺快照不重複；同一 `(ID,月份)` 若代表不同原始職缺需先修正來源鍵。
舊 DB 若不符合報告所述 schema，請先取得欄位結構再調整，不要硬改正式 DB。

報告用語必須區分：

- long-only 的 jobs 範圍是來源 long 中出現的快照，不能據此推算全體漏抓數。
- raw_source_job_snapshots 與 jobs_not_in_raw_sources 顯示原始資料覆蓋；匯入原始檔本身是否完整仍需核對上游資料。
- `jobs_without_detail_rows` 是「目前沒有技能明細的快照」，可能尚未擷取，不能直接稱漏抓。
- 有明細、名稱空白可能仍有有效技能 ID，不是零技能。
- 不同代碼使用同一名稱不代表跨分類，需核對 category/subcategory。
- distinct_nonempty_skill_ids/names 排除 NULL 與空字串；明細數包含全部來源列。
- 自我測試與人工範例不構成真實資料準確率；只有匯入目前取得的資料才能報實測筆數。

## SQL 查核

```sql
-- 月份必須參與關聯；計數單位為 jobs 的職缺快照
SELECT COUNT(*) AS jobs_without_detail_rows
FROM jobs j
WHERE NOT EXISTS (
  SELECT 1 FROM skill_records sr
  WHERE sr.ID=j.ID AND sr.資料月份=j.資料月份
);

-- 空中文名稱但有明細；仍需對照實際詞庫
SELECT record_id, ID, 資料月份, SKILL_ID, Skill_Name_ZH, category, subcategory
FROM v_skill_long
WHERE record_id IS NOT NULL AND Skill_Name_ZH=''
ORDER BY ID, 資料月份, record_id;

-- 找到多個技能代碼對應同一名稱的候選，這不是跨分類的證明
SELECT Skill_Name_ZH, COUNT(DISTINCT SKILL_ID) AS skill_id_count
FROM skill_records
WHERE TRIM(Skill_Name_ZH)<>'' AND TRIM(SKILL_ID)<>''
GROUP BY Skill_Name_ZH HAVING COUNT(DISTINCT SKILL_ID)>1;
```

## 餐飲、補教、醫療人工查核

補原始資料後，每類先匯出最多 50 筆候選。抽樣採固定 seed 的 reservoir sampling；
條件是職稱代理，**industry_confirmed 留空供人工核對真正產業**。
人工查核 CSV 會含職缺原文，留在忽略的 outputs 目錄中。

```bash
.venv/bin/python scripts/export_skill_review.py --db skills_taichung_202609.db --industry 餐飲 --month 202609 --output outputs/review_food_202609.csv
.venv/bin/python scripts/export_skill_review.py --db skills_taichung_202609.db --industry 補教 --month 202609 --output outputs/review_education_202609.csv
.venv/bin/python scripts/export_skill_review.py --db skills_taichung_202609.db --industry 醫療 --month 202609 --output outputs/review_medical_202609.csv
```

另外加 `--no-detail` 並換輸出名稱，可抽查沒有技能明細的候選。
筆數不足時報告實際匯出量，不補造案例。

查核順序：

1. 確認真實產業與原文，核對 extracted_skills_json 的 ID、來源、分類。
2. 把誤抓的 record_id 填入 false_positive_record_ids，並貼原文證據。
3. 漏抓只能填實際詞庫中已驗證的 Skill_ID（missing_SKILL_IDs）；不能自行命名技能。
4. 填入整筆職缺的 expected_SKILL_IDs；用於之後按不重複技能 ID 計算 precision/recall。
5. 保存詞庫版本、擷取程式 commit、人工判定理由及審核者。保留一批未用於修規則的測試集。

餐飲優先查工作與供餐福利；補教區分教學、招生、教務與員工訓練；醫療區分工作技能、疾病名與科別。
名稱缺失先查同一 Skill_ID 在真實詞庫中的 Skill_Name_ZH、英文名稱及關鍵字；只補已確認的翻譯，
不因名稱空白而刪除技能 ID。既有 long 沒有確切命中詞／位置時，不能從 MATCHED_FROM 倒推出命中證據。
真正的零命中、誤抓、漏抓以及三產業指標，都需要原始資料與人工標註後才可宣稱。
