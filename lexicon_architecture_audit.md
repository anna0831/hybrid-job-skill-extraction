# 104 技能擷取系統：詞庫架構實證審計報告
**檔案名稱**：`lexicon_architecture_audit.md`  
**審計日期**：2026 年 10 月 03 日  
**審計人員**：Python Data Engineer & Research Software Reviewer  
**審計目標**：檢視儲存庫中程式碼與最新詞庫檔案，確立詞庫 Source of Truth，研判架構型態，並提供客觀量化比對數據以供會議審查。

---

## 一、目前的 Source of Truth 與程式讀取現況 (Section A)

經檢視程式碼 [104_single_file_20260930.py](104_single_file_20260930.py) 與儲存庫目錄結構，現況如下：

### 1. 程式預設讀取路徑
在 `104_single_file_20260930.py` 第 98–101 行中，程式宣告之預設常數為：
```python
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 優先採用根目錄最新 0930 詞庫，若不存在則相容退回 outputs/temp/0918 詞庫
_DEFAULT_LEX = "詞庫skill_lexicon_v13_20260930.xlsx" if os.path.exists(os.path.join(BASE_DIR, "詞庫skill_lexicon_v13_20260930.xlsx")) else "outputs/temp/詞庫skill_lexicon_v13_20260918.xlsx"
LEXICON_PATH = os.path.join(BASE_DIR, _DEFAULT_LEX)
GROUPED_LEXICON_PATH = os.path.join(BASE_DIR, "詞庫skill_lexicon_v13_Chen_grouped_09_2026.xlsx")
```
- **基底詞庫現狀**：程式預設優先使用 0930（根目錄最新版 `詞庫skill_lexicon_v13_20260930.xlsx`）；若該檔不存在，則自動相容 fallback 至 `outputs/temp/詞庫skill_lexicon_v13_20260918.xlsx`。
- **執行狀態**：具備自動檢測與相容退回機制，直接執行不會發生 `FileNotFoundError`。

### 2. 詞庫在 Pipeline 各階段的使用
| 檔案名稱 | 實質功能與用途 | 關鍵使用欄位 | 使用階段 |
| :--- | :--- | :--- | :--- |
| **`詞庫skill_lexicon_v13_20260930.xlsx`**<br>(根目錄最新版) | **字串比對與 AC 自動機基底**：提供標準中英文名稱、雙語觸發關鍵字（Keywords）與兩字詞放行名單。 | `Skill_ID`, `Skill_Name`, `Skill_Name_ZH`, `Keywords`, `Category_Name`, `Subcategory_Name`, `Category_Code`, `Subcategory_Code`, `Skill_Type`, `Allow_Bare_2Char_Keywords` | **步驟 1 / 階段一**：<br>`load_automaton()` 內部建構 Trie 樹、Failure 鏈接與 jieba 自訂詞典。 |
| **`詞庫skill_lexicon_v13_Chen_grouped_09_2026.xlsx`**<br>(根目錄分類元資料) | **新十大主分類 Metadata 提供者**：提供對應至 Word 規範之十大分類代碼與標準中文名稱。 | `Skill_ID`, `Skill_group10`, `Skill_group10_code`, `Grouping_rule` | **步驟 1 / 階段二**：<br>`load_grouping_metadata()` 預載為 `id_to_group10` 查詢字典，供配對命中時注入屬性。 |

---

## 二、0930 最新詞庫 Schema 與欄位核實 (Section B)

以 Python 讀取 `詞庫skill_lexicon_v13_20260930.xlsx`（共 26,578 列，涵蓋 26,315 個唯一 Skill_ID，14 個欄位）：

- **工作表名稱**：`['Sheet1']`
- **欄位清單**：
  `Category_Code`, `Category_Name`, `Subcategory_Code`, `Subcategory_Name`, `Skill_ID`, `Skill_Name`, `Skill_Type`, `Frequency`, `Source`, `Skill_Category_No`, `Skill_Category`, `Skill_Name_ZH`, `Keywords`, `Allow_Bare_2Char_Keywords`

### 欄位存在性查核
| 查核欄位 | 0930 詞庫狀態 | 說明 |
| :--- | :---: | :--- |
| `SKILL_ID` | **存在** | 欄位名稱為 `Skill_ID` |
| `SKILL_NAME` | **存在** | 欄位名稱為 `Skill_Name` |
| `SKILL_NAME_ZH` | **存在** | 欄位名稱為 `Skill_Name_ZH` |
| `Keywords` | **存在** | 欄位名稱為 `Keywords` |
| `Category_Name` | **存在** | 欄位名稱為 `Category_Name` |
| `Subcategory_Name` | **存在** | 欄位名稱為 `Subcategory_Name` |
| `Category_Code` | **存在** | 欄位名稱為 `Category_Code` |
| `Subcategory_Code` | **存在** | 欄位名稱為 `Subcategory_Code` |
| `Skill_group10` | **不存在** | 0930 詞庫中無此欄位 |
| `Skill_group10_code` | **不存在** | 0930 詞庫中無此欄位 |
| `Grouping_rule` | **不存在** | 0930 詞庫中無此欄位 |
| `Grouping_status` | **不存在** | 0930 詞庫中無此欄位 |
| `IS_SOFTWARE` | **不存在** | 屬程式內部計算衍生屬性，詞庫檔案中無此欄 |

> **說明**：`詞庫skill_lexicon_v13_20260930.xlsx` 保留既有的 `Skill_Category_No`（0~9）與 `Skill_Category`（如 *Advanced Computer Skills*, *Cognitive Skills*, *AI & Big Data Skills* 等舊九類體系），未包含新版十大主分類。

---

## 三、詞庫架構判斷 (Section C)

依據實際檔案查核與實證數據，目前系統架構屬於：

### 🎯 **Case 2：0930 仍然只是技能 matching 基底，十大分類仍需要另一份 classification lexicon**

#### 判定依據：
1. **0930 詞庫為比對基底**：包含標準技能名稱與觸發關鍵字，但無新十大主分類欄位。
2. **Chen 版詞庫為十大分類來源**：儲存庫中收錄新十大主分類代碼（1~10）與標準中文名稱的檔案為 `詞庫skill_lexicon_v13_Chen_grouped_09_2026.xlsx`。
3. **結論**：為產出固定 25 欄位的 Long format 資料，程式目前維持雙軌架構：以 0930 版作為比對基底，並以 Chen_grouped_09 版提供十大分類 metadata。

---

## 四、實證量化比對與分析

### 1. 0930 Skill_ID 在 Chen 分類詞庫中的 mapping coverage
- 0930 包含 26,315 個不重複 Skill_ID。
- 其中 26,310 個可在 Chen_grouped_09 找到對應記錄。
- **0930 Skill_ID 在 Chen 分類詞庫中的 mapping coverage 為 99.98%（26,310 / 26,315）**。
- 0930 中存在、但 Chen 版缺少十大分類 metadata 的 Skill_ID 共 5 筆（0.02%）。

### 2. 5 筆未在 Chen 取得十大分類 metadata 之技能
| Skill_ID | 0930 中文名稱 | Lightcast Category / Subcategory | 目前處理方式 |
| :--- | :--- | :--- | :--- |
| `TW_PERS_001` | 中式整復推拿 | Personal Care / Beauty & Body Treatments | 技能仍保留；分類碼與名稱為空；狀態為「未對應」 |
| `TW_TCM_002` | 中醫特殊療法與科別 | Health Care / Alternative Therapy | 技能仍保留；分類碼與名稱為空；狀態為「未對應」 |
| `TW_NUR_010` | 病患移位與基礎照護技術 | Health Care / Nursing & Patient Care | 技能仍保留；分類碼與名稱為空；狀態為「未對應」 |
| `TW_MED_002` | 健保申報與門診行政 | Health Care / Health Care Administration | 技能仍保留；分類碼與名稱為空；狀態為「未對應」 |
| `TW_SOC_002` | 身心障礙職業重建服務 | Social Services / Government Assistance | 技能仍保留；分類碼與名稱為空；狀態為「未對應」 |

> 目前處理方式：0930 詞庫仍包含這 5 個 Skill_ID，但在目前 Chen_grouped_09 中未找到對應的十大分類 metadata。因此目前程式中該技能仍保留，Skill_group10_code 為空，Skill_group10 為空，Grouping_status 為未對應，列入會議討論。

### 3. 0918 存在但 0930 移除之 11 筆 Skill_ID 查核
經逐筆比對 0918 與 0930，共有 11 筆 Skill_ID 僅存在於 0918。比對其技能名稱與 0930 詞庫內容，變更情形如下：

| 0918 Skill_ID | 0918 中文名稱 (Skill_Name_ZH) | 0918 英文名稱 (Skill_Name) | 0930 同名技能 Skill_ID | 變更情形說明 |
| :--- | :--- | :--- | :--- | :--- |
| `TW_ACCT_001` | 會計作業 | Accounting Operations | `ES5A48B64B63BC943CF3` | 0918 原已存在該 ES 代碼；0930 移除自編 TW 碼，並將其關鍵字併入該 ES 代碼 |
| `TW_BOM_001` | 物料清單 | Bill of Materials (BOM) | `BGS10F94E4049444B523` | 0918 原已存在該 BGS 代碼；0930 移除自編 TW 碼，並將其關鍵字併入該 BGS 代碼 |
| `TW_ECN_001` | 工程變更通知 | Engineering Change Notice (ECN) | `KS123JZ6QB97DN4WD42W` | 0918 原已存在該 KS 代碼；0930 移除自編 TW 碼，並將其關鍵字併入該 KS 代碼 |
| `TW_FB_001` | 食材備料 | Food Preparation | `KS1241J6ZY2S66SZG3QS` | 0918 原已存在該 KS 代碼（食物準備）；0930 移除自編 TW 碼，並將備料關鍵字併入該 KS 代碼 |
| `TW_NUR_001` | 護理評估 | Nursing Assessment | `KS1274W63QXZT52GW1RF` | 0918 原已存在該 KS 代碼；0930 移除自編 TW 碼，並將其關鍵字併入該 KS 代碼 |
| `TW_NUR_002` | 傷口護理 | Wound Care | `KS442546YGKQC49SH18W` | 0918 原已存在該 KS 代碼；0930 移除自編 TW 碼，並將其關鍵字併入該 KS 代碼 |
| `TW_PROC_CTRL_001` | 製程控制 | Process Control | `KS1281Y6QHJ8PQLHTZ6R` | 0918 原已存在該 KS 代碼；0930 移除自編 TW 碼，並將其關鍵字併入該 KS 代碼 |
| `TW_RETAIL_002` | 補貨上架 | Shelf Restocking | `KSD9RL4YOWYBKJ1EOKNB` | 0918 原已存在該 KS 代碼；0930 移除自編 TW 碼，並將其關鍵字併入該 KS 代碼 |
| `TW_RETAIL_004` | 商品管理 | Merchandise Management | `ESB35D9808E206D5D59A` | 0918 原已存在該 ES 代碼；0930 移除自編 TW 碼，並將其關鍵字併入該 ES 代碼 |
| `TW_SEC_002` | 巡邏勤務 | Security Patrol | （無同名記錄；相關詞併入 `KS127LW62SG0TTVKDYQJ` 巡邏） | 0930 移除自編 TW 碼，巡邏勤務關鍵字併入既有之巡邏技能 |
| `TW_SUPPLY_001` | 供應鏈管理 | Supply Chain Management | `KS440C365HRHPM9VQDFF` | 0918 原已存在該 KS 代碼；0930 移除自編 TW 碼，並將其關鍵字併入該 KS 代碼 |

> **說明**：比對顯示上述自編 TW 代碼在 0918 中與既有之 Lightcast 代碼並存，0930 版移除了上述 11 筆自編代碼，並將其觸發關鍵字併入對應的既有技能中。

### 4. Category / Subcategory 一致性查核
在 0918 與 0930 可比較的 26,315 筆共同 Skill_ID 中：
- `Category_Name` 不一致：**0 筆**
- `Subcategory_Name` 不一致：**0 筆**
- `Category_Code` 不一致：**0 筆**
- `Subcategory_Code` 不一致：**0 筆**

在此次共同 Skill_ID 比對中，未觀察到 Category_Name 或 Subcategory_Name 差異。

### 5. Keywords 差異統計定義
- 在 26,315 筆共同 Skill_ID 中，共有 **30 筆技能**之 `Keywords` 欄位存在字串內容差異（其餘 26,285 筆完全一致）。
- 差異內容主要為前述 10 餘筆技能吸收了移除自編碼之中文關鍵字，以及少數職缺常見詞（如文書工作加入「內勤文書」、工程變更通知加入「ECN」等）。
- 不重複技能的關鍵字 token 總數由 0918 的 94,731 個微幅增至 0930 的 94,744 個（淨增 13 個 token）。
- （先前提及之 69,460 筆係源於多重類別交叉合併產生之資料列計數，並非不重複技能數，不列入正式文件）。

### 6. 500 筆測試資料輸出比對
以 `data/demo/demo_彰化縣_202608_500.xlsx` 進行比較：
- 0918 產生 3,953 筆技能列；0930 產生 3,954 筆技能列。
- 兩者皆有 496 筆職缺至少命中一項技能。
- 0930 相較 0918 新增 1 筆技能命中；該新增結果是否屬於正確擷取，仍需人工核對。
- 共同命中對（ID, SKILL_ID）共 3,925 組；差異部分主要源於前述自編代碼轉換為既有代碼（例如原本命中 `TW_BOM_001` 改為命中 `BGS10F94E4049444B523`）。

---

## 五、Python 程式修改評估

1. **實作狀態**：[104_single_file_20260930.py](104_single_file_20260930.py) 第 98–100 行已完成設定：優先使用 0930（根目錄最新版 `詞庫skill_lexicon_v13_20260930.xlsx`），若不存在則相容 fallback 至 `outputs/temp/詞庫skill_lexicon_v13_20260918.xlsx`。
2. **架構維持**：維持雙軌架構，保留 `詞庫skill_lexicon_v13_Chen_grouped_09_2026.xlsx` 作為十大分類 metadata 來源。
3. **演算法保持**：不更動 AC matching 演算法、`seen_zh_terms`、消歧規則或既有分類邏輯。
4. **輸出規格保持**：維持 25 個固定欄位與既有排序。
