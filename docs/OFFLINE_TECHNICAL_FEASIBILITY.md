# 離線雙擊版 `web-offline/app.html` 技術可行性評估報告

> 評估日期：2026-11-14  
> 適用引擎：`11/14 AC + Rules Pipeline`（`104_single_city_merged_20261114.py` / `src/web_adapter.py` / `src/ac_rules_1114.py`）

---

## 1. Python 依賴與資料格式盤點

針對現行正式 Web 引擎（`src/web_adapter.py` + `src/ac_rules_1114.py`），逐一盤點其執行依賴：

| Python 模組 / 套件 | 用途 | 瀏覽器 `file://` 替代方案 | 實作狀態 |
| :--- | :--- | :--- | :--- |
| `pyahocorasick` | 多關鍵字 Aho-Corasick 自動機比對 | 純 JavaScript `AhoCorasick` 類別（Trie + BFS failure links + 最長匹配不重疊掃描） | ✅ **完整移植**（`web-offline/vendor/engine_1114.js`） |
| `jieba` | 中文分詞（DAG 動態規劃 + HMM Viterbi + `addWord`）與長詞/協調尾詞保護 | 純 JavaScript `JiebaLite`（`web-offline/vendor/jieba_lite.js`）+ 內建 gzip/base64 MIT `dict.txt` 與 HMM 機率表（`web-offline/vendor/jieba_dict.js`） | ✅ **逐詞比對一致** |
| `re` | `src/ac_rules_1114.py`（56 條上下文排除、21 條縮寫佐證、否定句 `_NEGATION_RE`）與段落標題切分 | 原生 JS `RegExp`；經自動掃描確認 `src/ac_rules_1114.py` 含 `0` 個 JS 不支援之特殊正則語法，並由 `rules_1114_data.js` 完整匯出 | ✅ **完整移植** |
| `openpyxl` | 讀取上傳 `.xlsx` 與匯出 4 工作表 `.xlsx`（`Skills_Long`, `Group10_Summary`, `Jobs`, `Audit`） | 零外部依賴純 JS ZIP + XML 讀寫器 `XlsxLite`（原生 `DecompressionStream('deflate-raw')` / `CompressionStream('deflate-raw')`） | ✅ **已與 `openpyxl` 雙向驗證** |
| `gzip` / `json` / `hashlib` | 讀取 `lexicon_bundle.json.gz` 並計算 SHA256 | 瀏覽器原生 `File API` + `DecompressionStream('gzip')` + `crypto.subtle.digest('SHA-256')` | ✅ **原生支援** |
| `nltk` | 未使用於 `src/web_adapter.py` / `src/ac_rules_1114.py` | 不需移植 | — |

---

## 2. 為何不採用 Pyodide / WebAssembly，而採用純 JS 轉譯？

1. **`file://` 協定 CORS 限制**：在 Chrome 直接雙擊 HTML（`origin: 'null'`）時，瀏覽器會封鎖 `fetch()` 與 `<script type="module">`。Pyodide 與多數 WASM 載入器依賴 `fetch()` 下載 `.wasm` 與 `.whl` 檔案，在 `file://` 下會直接觸發 CORS 錯誤而失敗，且需要連線 CDN 或啟動本機 HTTP 伺服器。
2. **純傳統 `<script src="./vendor/...">` + 瀏覽器原生 API**：
   - 傳統 `<script src="./vendor/...">` 可在 `file://` 下合法載入同目錄或子目錄之本機 JS 檔案，完全不觸發 CORS 或網路請求。
   - 無須 CDN、無須 `localhost`、無須安裝 Python 或執行任何終端機指令。
   - 啟動時間僅數百毫秒，遠快於 Pyodide 初始化（數十 MB 下載與解譯）。

---

## 3. 詞庫安全隔離設計

- **嚴禁內嵌與提交**：正式詞庫 `詞庫skill_lexicon_v13_20261111z.xlsx`（26,471 技能）與 `G11c` 十大分類**未**內嵌於 `web-offline/app.html` 或任何 JS 檔案中，亦不會提交至公開 GitHub。
- **本機 File API 選檔**：研究助理開啟 `web-offline/app.html` 後，透過 `<input type="file" accept=".gz,.json">` 手動選取本機的 `web_data/lexicon_bundle.json.gz`，瀏覽器僅於本機記憶體中使用 `DecompressionStream('gzip')` 解壓並建置 AC 自動機與 SHA256 雜湊驗證，全程零上傳、零網路傳輸。

---

## 4. CLI 等價性驗證結果

以臺中市 202609 職缺（`seed=42`，兼職排除後 100 筆）與正式研究主線 `104_single_city_merged_20261114.py` 進行逐筆比對：

| 驗收指標 | 11/14 Python CLI | 離線版 JS Engine (`web-offline`) | 一致性結果 |
| :--- | :---: | :---: | :---: |
| `Skill_ID ExactMatch` | 100 筆基準 | **100 / 100** | ✅ **完全一致** |
| 技能命中總列數 | 884 | **884** | ✅ **完全一致** |
| 零技能職缺數 | 4 | **4** | ✅ **完全一致** |
| `G1–G10` 分類差異 | — | **0 筆差異** | ✅ **完全一致** |
| `Is_AI_Skill` 旗標差異 | — | **0 筆差異** | ✅ **完全一致** |
| Audit `exclude` 紀錄 | 35 | **35**（`onlyCliExcl=[]`, `onlyJsExcl=[]`） | ✅ **完全一致** |
| Audit `keep` 備註紀錄 | — | **3**（總 Audit 38 筆） | ✅ **與 Web 版一致** |

### 邊界規則驗證（9 項測試全數通過）
- **否定句排除**：`無需Python`、`不需會Excel`、`不用駕駛汽車`、`不必具備AutoCAD`、`免英語能力` 均正確進入 Audit `exclude`。
- **縮寫與多義消歧**：`GCP`（區分 Google Cloud Platform 與臨床試驗 GCP）、`GDP`（區分良好分銷規範 GDP 與經濟指標）、`PCI`（區分 PCIe/PCI 與支付卡產業 PCI）、`Go`（區分 Go 語言與英文動詞 `We go together`）皆正確保留或排除。
- **福利文案排除**：`【公司福利】` 內誤命中之非工作技能正確排除。
- **大小寫與結構化欄位**：`Case_Sensitive_Keywords` 與 `Structured_Field_Exact_Tags`（`工作技能`、`電腦工具`）皆正確對應。

---

## 5. 已知限制

1. **詞庫檔案需由使用者選取**：基於詞庫授權與公開 Repo 安全，開啟頁面後須先選取本機 `lexicon_bundle.json.gz`。
2. **批次上限 100 筆**：為維持瀏覽器單執行緒反應流暢度，Excel 批次匯入上限比照 Web 版設為 100 筆（並自動排除 `工作角色 == "兼職"`）。
3. **瀏覽器需求**：需支援 `DecompressionStream('gzip')` 與 `DecompressionStream('deflate-raw')` 的現代瀏覽器（Chrome 80+ / Edge 80+ / Safari 16.4+，建議使用 Google Chrome）。

