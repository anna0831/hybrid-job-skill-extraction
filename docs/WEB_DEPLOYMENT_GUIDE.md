# 104 職缺技能擷取 Vercel 教授展示版 — 部署與維運指南 (`WEB_DEPLOYMENT_GUIDE`)

## 1. 事前準備：轉換 11/11 正式詞庫

由於 11/11 正式詞庫（`詞庫skill_lexicon_v13_20261111g.xlsx` 與 `詞庫skill_lexicon_v13_Chen_grouped_11_2026c.xlsx`）體積較大且位於研究專案詞庫目錄，Vercel API 不會在每次請求讀取 `.xlsx`。部署前請先在本機執行一次轉換腳本，產生唯讀壓縮詞庫 `web_data/lexicon_bundle.json.gz`：

```bash
source .venv/bin/activate
python scripts/prepare_web_lexicon.py \
  --base-lexicon "/Users/anna/Library/CloudStorage/OneDrive-個人/ChenRA/AI_Job_project/詞庫/詞庫skill_lexicon_v13_20261111g.xlsx" \
  --grouped-lexicon "/Users/anna/Library/CloudStorage/OneDrive-個人/ChenRA/AI_Job_project/詞庫/詞庫skill_lexicon_v13_Chen_grouped_11_2026c.xlsx" \
  --output web_data/lexicon_bundle.json.gz
```

> 若只放在專案根目錄或 `lexicon/` 下，也可直接執行 `python scripts/prepare_web_lexicon.py`。

---

## 2. 本機啟動與測試指令

```bash
source .venv/bin/activate
uvicorn api.index:app --host 127.0.0.1 --port 8000 --reload
```

開啟瀏覽器訪問：`http://127.0.0.1:8000/`

執行自動化測試（含 API、AC + Rules、G1–G10、GCP/福利規則與 100 筆 `.xlsx` 4 工作表驗證）：

```bash
.venv/bin/pytest -v tests/test_web_api.py
```

---

## 3. Vercel 部署檢查項目（Phase 5 實測評估）

1. **Python Runtime 相容性**：`api/index.py` 使用標準 ASGI (`FastAPI` / `Starlette`)，與 Vercel Python 3.12 runtime 相容。
2. **Build Dependencies 與 Bundle Size（250 MB 上限）**：
   - `src/web_adapter.py` 已完全移除 `pandas`、`numpy`、`pyarrow`、`nltk`、`streamlit`、`torch`。
   - 請在 Vercel 專案設定中指定使用 `requirements-vercel.txt`（或確保部署時不安裝 `requirements.txt` 中的重型科學計算套件），可將 unzipped bundle 控制在 ~50 MB 內。
3. **Cold Start 與唯讀檔案系統**：
   - 已於 `src/web_adapter.py` 設定 `jieba.dt.tmp_dir = "/tmp"`，避免寫入唯讀 `/var/task`。
   - AC 自動機在模組層以 Singleton 快取，Cold Start 約 0.5–1.5 秒，Warm Request 單篇 < 50 ms。
4. **Timeout 與 Response Size（4.5 MB 上限）**：
   - `vercel.json` 設定 `maxDuration: 30`（Hobby 方案預設上限為 10s；Pro 方案可達 30–60s）。
   - 100 筆職缺的 `.xlsx` 在記憶體 `BytesIO` 壓縮輸出，一般約 100–800 KB；若未來出現極端長文導致 `.xlsx` 超過 4.5 MB，請改採「替代架構」。
5. **部署費用風險**：
   - LLM、MockLLM 與 Embedding 已完全停用，**無任何 AI API 費用**。
   - API 已限制單次最多 100 筆、單篇工作內容上限 30,000 字元，且 Log 不印出職缺原文。

---

## 4. 替代部署架構建議（當完整 11/11 詞庫超過 Vercel 免費方案限制時）

若完整 `20261111g` 詞庫載入後記憶體超過 Vercel Hobby 方案上限，或 100 筆長文 `.xlsx` 超過 4.5 MB Response 上限，建議採用 **前後端分離架構**（不縮減詞庫也不改寫為假資料）：

- **前端（Vercel Static Hosting）**：僅部署 `web/`（純 HTML/CSS/JS，零費用、全球 CDN）。
- **後端（Render / Railway / Google Cloud Run）**：以 Docker 執行 `uvicorn api.index:app --host 0.0.0.0 --port $PORT`，掛載 `web_data/lexicon_bundle.json.gz`，透過環境變數 `ALLOWED_ORIGINS` 允許 Vercel 前端網域跨網域存取。
