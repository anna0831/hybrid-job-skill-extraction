# Research Version Changelog: 2026/11/11 Baseline vs. 2026/11/14 Candidate

本文件記錄研究引擎與詞庫自 **2026/11/11 Baseline** 升級至 **2026/11/14 Candidate** 的版本差異、檔案雜湊值（SHA256）、規則與詞庫變更，以及已知未同步項目。

---

## 1. 版本檔案與 SHA256 對照

| 項目 | 2026/11/11 Baseline | 2026/11/14 Candidate | 狀態 |
| :--- | :--- | :--- | :--- |
| **擷取主程式** | `104_single_city_merged_20261111.py`<br>SHA256: `7abf4a03d0479f8447a84a3b2653ecffefa5a9aaf59ad613d81399f178da21d8` | `104_single_city_merged_20261114.py`<br>SHA256: `7af3037ef3d27b0f8d12311787a785cb8d83e359d10ed403327984485864b521` | 已整合至 `src/ac_rules_1114.py` 與 `src/web_adapter.py` |
| **基底詞庫** | `詞庫skill_lexicon_v13_20261111g.xlsx`<br>SHA256: `12d2f050e8e11ec972e84a5c45aa57b32c659836234f367568eca70340156e13`<br>技能數：26,461（26,461 唯一 `Skill_ID`） | `詞庫skill_lexicon_v13_20261111z.xlsx`<br>SHA256: `722cd2832ffab71b5cee08e1397b890bb6330962194220ed4ca301f7549160bf`<br>技能數：26,471（26,471 唯一 `Skill_ID`） | 已編譯為 `web_data/lexicon_bundle.json.gz`（26,471 技能，315 AI 技能） |
| **十大分類對應表 (G11c)** | `詞庫skill_lexicon_v13_Chen_grouped_11_2026c.xlsx`<br>SHA256: `e35b53bf5ad3f1da77f25874689f5e1abbe62f22780b31c71ff10f132a3a16bb`<br>技能列數：26,616（26,616 唯一 `Skill_ID`） | `詞庫skill_lexicon_v13_Chen_grouped_11_2026c.xlsx`（OneDrive 2026/11/13 13:43 版）<br>SHA256: `31f5e3e2beeba33788d45ebec3eb156479e21d1470b8126e4ac151b328947048`<br>技能列數：26,626（26,626 唯一 `Skill_ID`） | 已同步至本機並重新編譯 `web_data/lexicon_bundle.json.gz`（未加入 Git） |

> [!IMPORTANT]
> 11/11 Baseline 檔案均完整保留於專案目錄，未覆蓋或刪除。

---

## 2. 詞庫變更摘要（`1111g` → `1111z`）

- **總技能數**：`26,461` → `26,471`（+10 項，0 項刪除）
- **新增 10 項技能**：
  1. `TW_AI_001` — Midjourney（AI 技能）
  2. `TW_AI_002` — Runway AI影片生成（AI 技能）
  3. `TW_AI_003` — Perplexity（AI 技能）
  4. `TW_JIBAO_001` — 集保作業
  5. `TW_SEMI_020` — CPLD複雜可程式邏輯元件
  6. `TW_SW_005` — HTTP協定
  7. `TW_SW_006` — WPS Office
  8. `TW_SW_007` — Corel Painter
  9. `TW_SW_008` — CoolDraw
  10. `TW_SW_009` — dBase
- **欄位異動統計**：
  - `Keywords` 變更：`2,186` 項（清理泛稱關鍵字與修正同義詞）
  - `Category` 變更：`0` 項
  - `Case_Sensitive_Keywords` 變更：`4` 項
  - `Structured_Field_Exact_Tags` 變更：`17` 項
- **特別欄位支援**：`Case_Sensitive_Keywords` 與 `Structured_Field_Exact_Tags` 於 11/11 與 11/14 皆維持完整支援，已於 `scripts/prepare_web_lexicon.py` 與 `src/web_adapter.py` 保留處理邏輯。

---

## 3. 引擎規則變更摘要（`20261111` → `20261114`）

11/14 研究版規則已抽離至獨立共用模組 `src/ac_rules_1114.py`（`CODE_VERSION = "20261114_web_ac_v1"`、`RULE_VERSION = "ac_rules_20261114"`），由 Web 引擎 `src/web_adapter.py` 直接匯入：

1. **否定句排除（`_NEGATION_RE` + `is_negated()`）**：
   - 於 `職位描述` 欄位（`orig_s > 0`）檢查前綴否定詞：`無需`、`不需`、`不用`、`不必`、`免`，避免將「無需經驗 / 免經驗 / 不用會 Python」誤判為需求技能。
2. **福利、公司介紹與招募文案排除（`_BENEFIT_WORDS`、`_HEALTH_CHECK_REQ`）**：
   - 新增員工福利（如健檢、團保、三節獎金、員工旅遊等）與招募文案語境過濾，避免「員工健檢」誤命中醫療技能或「員工福利」誤命中 HR 技能。
3. **擴充語境排除規則（`_CONTEXT_EXCLUSION_RULES`，共 56 條）**：
   - 新增 30+ 條前後 50 字語境排除規則，涵蓋門市商品管理／銷售管理、IC 設計 `IPs`、健康檢查、公司福利等一詞多義誤命中情境。
4. **擴充縮寫與一詞多義消歧（`_ACRONYM_CONTEXT_REQUIRED`，共 21 條）**：
   - 支援 5-tuple 格式 `(acronym, window, patterns, near_deny, near_w)` 與 `_SW_NEAR` 軟體鄰近詞檢查。
   - 強化 `GCP`、`GDP`、`PCI`、`Go`、`CTO` 等縮寫與多義詞在 150–300 字領域佐證視窗下的消歧邏輯。

---

## 4. G11c 十大分類與 AI 技能標記驗證（2026/11/13–11/14）

### 4.1 G11c 更新驗證（SHA256: `31f5e3e2beeba33788d45ebec3eb156479e21d1470b8126e4ac151b328947048`）
- **總技能列數**：`26,616` → `26,626`（+10 項，0 筆衝突）。
- **新增 10 項技能分類**：
  - `TW_AI_001`（Midjourney）、`TW_AI_002`（Runway AI影片生成）、`TW_AI_003`（Perplexity）、`TW_SW_005`（HTTP協定）、`TW_SW_007`（Corel Painter）、`TW_SW_008`（CoolDraw）、`TW_SW_009`（dBase）→ **G8（資訊科技、軟體、資料與AI技能）**
  - `TW_JIBAO_001`（集保作業）→ **G4（財務、會計與經濟技能）**
  - `TW_SW_006`（WPS Office）→ **G6（行政與一般數位技能）**
  - `TW_SEMI_020`（CPLD複雜可程式邏輯元件）→ **G10（工程、自然科學、設計、環境與能源技能）**
- **`n8n` 分類修正**：`ES20955CC91DB8F5D8E3`（N8n）由 G10 改列 **G8（資訊科技、軟體、資料與AI技能）**。
- **8 項 TW-ONET 誤分類修正（11/13 `Ambiguity_note` 標註原 Category 誤標 Health Care/Cardiology）**：
  1. `TW1B855476BFC545DC95`（Engineering And Technology）→ **G10**
  2. `TW3E7BD7A672DF4B618E`（Production And Processing）→ **G7**
  3. `TW0982AF61CDA34636B8`（Building And Construction，建築營造）→ **G10**（另 `TW_CONST_001` Construction Site Inspection and Safety Maintenance 為 **G7**）
  4. `TWAD7A599005F94BCFAC`（Food Production）→ **G7**
  5. `TWA9367BB761D942FD81`（Control Precision）→ **G3**
  6. `TWA24F5A48519F44CC9A`（Manual Dexterity，手工靈巧度）→ **G3**
  7. `TW8AB2052F89284713A2`（Arm-Hand Steadiness）→ **G3**
  8. `TW9E41EE20C31943B696`（Rate Control）→ **G3**

### 4.2 AI 技能標記差異（`Is_AI_Skill = 'Y'`）
- **11/11 Baseline（`1111g`）**：**312** 項
- **11/14 Candidate（`1111z`）**：**315** 項
- **新增標記（3 項）**：`TW_AI_001`（Midjourney）、`TW_AI_002`（Runway (AI Video)）、`TW_AI_003`（Perplexity AI）
- **取消標記（0 項）**：無
- **覆核狀態**：屬**尚待研究團隊人工確認之候選清單**，不可直接當作已驗證的人工 Gold Label；Web `/api/health` 依實際載入詞庫動態顯示 `Pending review (315 AI skills flagged)`。

### 4.3 Web / CLI 大小寫鄰近符號一致化修正
- 已將 `src/web_adapter.py` 的 `_is_lowercased_word_in_english()` 同步為 `104_single_city_merged_20261114.py` 規則（使用 `_RE_CJK_NEARBY` 檢查前後 6 字是否含中文或全形符號），修復 `0983111024．Line ID:protein1024` 在 Web 漏記 `exclude` Audit 的差異。

