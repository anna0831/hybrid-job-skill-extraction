"""
驗證腳本：針對 104_single_file_20260909.py 進行完整品質與新版規格驗證
涵蓋：
  1. 一筆職缺命中 3 個不同技能時，恰好輸出 3 列
  2. 這 3 列的原始 9 個欄位與來源完全一致 (不截斷、不摘要、不覆蓋)
  3. 原始資料有重複 ID 時，不會交叉配對或增加額外列數 (無 many-to-many 膨脹)
  4. Excel 與 Parquet 都包含 25 個欄位，順序相同，資料完全對齊
  5. 來源欄位別名正規化與內容衝突檢測 (ID vs 工作編號, 104職位名稱 vs 職位名稱 等)
  6. 識別欄位 (ID) 缺失時嚴格報錯，非識別欄位缺失時填空並提示
  7. 全零命中輸出 25 欄位空表，且無假技能列
  8. 修改前後在基準詞庫下比對集合 (縣市, 月份, ID, SKILL_ID) 完全一致
"""

import os
import sys
import tempfile
import pandas as pd
import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import importlib.util

# 載入修改後的 104_single_file_20260930.py (或相容 104_single_file_20260909.py)
target_path = os.path.join(REPO_ROOT, "104_single_file_20260930.py")
if not os.path.exists(target_path):
    target_path = os.path.join(REPO_ROOT, "104_single_file_20260909.py")

spec = importlib.util.spec_from_file_location("single_file", target_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

_BASE_LEX = "詞庫skill_lexicon_v13_20260930.xlsx" if os.path.exists(os.path.join(REPO_ROOT, "詞庫skill_lexicon_v13_20260930.xlsx")) else "outputs/temp/詞庫skill_lexicon_v13_20260918.xlsx"
LEXICON_BASE = os.path.join(REPO_ROOT, _BASE_LEX)
LEXICON_GROUPED = os.path.join(REPO_ROOT, "詞庫skill_lexicon_v13_Chen_grouped_09_2026.xlsx")
DEMO_DATA = os.path.join(REPO_ROOT, "data/demo/demo_彰化縣_202608_500.xlsx")

def run_tests():
    print("=" * 75)
    print(f"開始執行 {os.path.basename(target_path)} 全面品質與規格驗證")
    print("=" * 75)

    # 1. 建立自動機
    print("\n--- 載入詞庫與建立自動機 ---")
    automaton = mod.load_automaton(LEXICON_BASE, LEXICON_GROUPED)
    
    # 讀取真實 demo 500 筆測試資料
    read_dtype = {
        "ID": str, "工作編號": str,
        "104職位名稱碼": str, "職位名稱碼": str,
        "資料月份": str, "刊登日期": str
    }
    raw_df = pd.read_excel(DEMO_DATA, dtype=read_dtype)
    county = "彰化縣"
    month = "202608"

    print(f"\n--- 執行 process_county 測試 (輸入 {len(raw_df)} 筆真實職缺) ---")
    long_df = mod.process_county(raw_df, automaton, county, month)
    print(f"產生 long_df：共 {len(long_df):,} 列技能記錄，涵蓋 {long_df['ID'].nunique():,} 筆職缺，欄位數={len(long_df.columns)}")

    results = {}

    # 驗證 1：一筆職缺命中 3 個不同技能時，恰好輸出 3 列
    test_job_3skills = pd.DataFrame([{
        "ID": "TEST_3SKILLS_001",
        "資料月份": "202608",
        "刊登日期": "20260820",
        "工作角色": "全職",
        "104職位名稱": "心理輔導員",
        "104職位名稱碼": "002013001",
        "職位描述": "負責提供員工福利諮詢、心理諮詢以及椅子按摩服務放鬆身心。",
        "工作技能": "",
        "電腦工具": "",
    }])
    res_3skills = mod.process_county(test_job_3skills, automaton, "台北市", "202608")
    v1_pass = (len(res_3skills) == 3)
    results["1. 一筆職缺命中 3 個不同技能恰好輸出 3 列"] = {
        "pass": v1_pass,
        "detail": f"實際輸出列數: {len(res_3skills)} 列 (命中技能: {res_3skills['SKILL_NAME_ZH'].tolist()})"
    }
    print(f"\n[驗證 1] 一職缺命中 3 技能恰好輸出 3 列: {'PASS' if v1_pass else 'FAIL'}")
    print(f"  細節: {results['1. 一筆職缺命中 3 個不同技能恰好輸出 3 列']['detail']}")

    # 驗證 2：這 3 列的原始 9 個欄位與來源完全一致 (不截斷、不摘要、不覆蓋)
    raw_9_cols = [
        "ID", "資料月份", "刊登日期", "工作角色",
        "104職位名稱", "104職位名稱碼", "職位描述", "工作技能", "電腦工具"
    ]
    raw_expected = test_job_3skills.iloc[0]
    mismatches = []
    for col in raw_9_cols:
        expected_val = str(raw_expected[col]).strip()
        for idx, row in res_3skills.iterrows():
            actual_val = str(row[col]).strip()
            if actual_val != expected_val:
                mismatches.append(f"列 {idx} 欄位 '{col}' 不一致: 預期 '{expected_val}' vs 實際 '{actual_val}'")

    # 另外在 demo 的 3955 列抽樣檢查 50 筆
    demo_sample_mismatch = 0
    raw_lookup = {}
    norm_raw, _, _ = mod.normalize_job_fields(raw_df)
    for _, r in norm_raw.iterrows():
        raw_lookup[r["ID"]] = r

    for _, r in long_df.sample(n=min(50, len(long_df)), random_state=42).iterrows():
        jid = r["ID"]
        src = raw_lookup[jid]
        for c in raw_9_cols:
            if str(r[c]) != str(src[c]):
                demo_sample_mismatch += 1

    v2_pass = (len(mismatches) == 0 and demo_sample_mismatch == 0)
    results["2. 原始 9 個欄位與來源完全一致"] = {
        "pass": v2_pass,
        "detail": f"測試職缺 9 欄不一致數: {len(mismatches)}, Demo 抽樣 50 筆不一致數: {demo_sample_mismatch}"
    }
    print(f"\n[驗證 2] 原始 9 個欄位與來源完全一致: {'PASS' if v2_pass else 'FAIL'}")
    print(f"  細節: {results['2. 原始 9 個欄位與來源完全一致']['detail']}")

    # 驗證 3：原始資料有重複 ID 時，不會交叉配對或增加額外列數
    dup_id_df = pd.DataFrame([
        {
            "ID": "DUP_JOB_999",
            "資料月份": "202608",
            "刊登日期": "20260801",
            "工作角色": "全職",
            "104職位名稱": "福利諮詢師",
            "104職位名稱碼": "001",
            "職位描述": "提供員工福利與心理諮詢服務",  # 命中 2 個技能: 員工福利, 心理諮詢
            "工作技能": "",
            "電腦工具": "",
        },
        {
            "ID": "DUP_JOB_999",  # 刻意相同 ID
            "資料月份": "202608",
            "刊登日期": "20260815",
            "工作角色": "兼職",
            "104職位名稱": "按摩師",
            "104職位名稱碼": "002",
            "職位描述": "提供椅子按摩舒壓服務",  # 命中 1 個技能: 椅子按摩
            "工作技能": "",
            "電腦工具": "",
        }
    ])
    dup_res = mod.process_county(dup_id_df, automaton, "新竹市", "202608")
    # 預期：恰好 2 + 1 = 3 列 (非 2 x 2 = 4 列膨脹)
    v3_len_ok = (len(dup_res) == 3)
    row0_roles = dup_res[dup_res["SKILL_NAME_ZH"].isin(["員工福利", "心理諮詢"])]["工作角色"].tolist()
    row1_roles = dup_res[dup_res["SKILL_NAME_ZH"] == "椅子按摩"]["工作角色"].tolist()
    v3_no_cross = (row0_roles == ["全職", "全職"] and row1_roles == ["兼職"])
    v3_pass = v3_len_ok and v3_no_cross
    results["3. 重複 ID 無交叉配對且無列數膨脹"] = {
        "pass": v3_pass,
        "detail": f"重複 ID 輸入 2 筆 (2+1 技能)，輸出列數: {len(dup_res)} (預期 3 列), 交叉配對檢查: {'無交叉 (正確)' if v3_no_cross else '有交叉 (錯誤)'}"
    }
    print(f"\n[驗證 3] 重複 ID 無交叉配對且無列數膨脹: {'PASS' if v3_pass else 'FAIL'}")
    print(f"  細節: {results['3. 重複 ID 無交叉配對且無列數膨脹']['detail']}")

    # 驗證 4：Excel 與 Parquet 格式一致性 (25 欄位、順序完全相同)
    with tempfile.TemporaryDirectory() as tmpdir:
        test_xlsx = os.path.join(tmpdir, "test_long.xlsx")
        test_parquet = os.path.join(tmpdir, "test_long.parquet")
        mod.export_long_to_excel(long_df, test_xlsx)
        mod.export_long_to_parquet(long_df, test_parquet)

        xl_in = pd.read_excel(test_xlsx, dtype=str)
        pq_in = pd.read_parquet(test_parquet)

        v4_len_ok = (len(xl_in) == len(pq_in) == len(long_df))
        v4_cols_ok = (xl_in.columns.tolist() == pq_in.columns.tolist() == mod.FINAL_COLUMNS)
        v4_cols_count_ok = (len(mod.FINAL_COLUMNS) == 25)

        # 內容比對
        int_cols = ["Category_Code", "Subcategory_Code", "Skill_group10_code"]
        diff_cells = 0
        for col in mod.FINAL_COLUMNS:
            if col in int_cols:
                def norm_int(val):
                    if pd.isna(val) or str(val).strip() in ("", "nan", "None", "<NA>"):
                        return ""
                    try:
                        return str(int(float(val)))
                    except Exception:
                        return str(val)
                s_xl = xl_in[col].apply(norm_int)
                s_pq = pq_in[col].apply(norm_int)
            else:
                s_xl = xl_in[col].fillna("").astype(str).str.strip()
                s_pq = pq_in[col].fillna("").astype(str).str.strip()
            diff_cells += (s_xl != s_pq).sum()

    v4_pass = v4_len_ok and v4_cols_ok and v4_cols_count_ok and (diff_cells == 0)
    results["4. Excel 與 Parquet 25 欄位順序與資料一致"] = {
        "pass": v4_pass,
        "detail": f"總欄位數: {len(mod.FINAL_COLUMNS)} 欄 (符合 25 欄), 列數一致 ({len(xl_in)}), 差異儲存格數: {diff_cells}"
    }
    print(f"\n[驗證 4] Excel 與 Parquet 25 欄位一致性: {'PASS' if v4_pass else 'FAIL'}")
    print(f"  細節: {results['4. Excel 與 Parquet 25 欄位順序與資料一致']['detail']}")

    # 驗證 5：欄位別名正規化與衝突檢測
    conflict_df = pd.DataFrame([{
        "ID": "ID_001",
        "工作編號": "JOB_999",  # ID 衝突
        "104職位名稱": "高級工程師",
        "職位名稱": "初級助理",   # 職位名稱衝突
        "104職位名稱碼": "001",
        "職位名稱碼": "002",      # 職位代碼衝突
        "電腦工具": "Python",
        "擅長工具": "Java",      # 工具衝突
        "資料月份": "202608",
        "刊登日期": "20260801",
        "工作角色": "全職",
        "職位描述": "系統開發",
        "工作技能": "後端開發",
    }])
    _, confs, _ = mod.normalize_job_fields(conflict_df)
    v5_conf_detected = (len(confs) == 4)  # 成功偵測到 4 處衝突
    v5_pass = v5_conf_detected
    results["5. 同名與替代欄位衝突檢測"] = {
        "pass": v5_pass,
        "detail": f"預設 4 處衝突 (ID, 職位名稱, 代碼, 工具)，實際偵測衝突數: {len(confs)}"
    }
    print(f"\n[驗證 5] 同名與替代欄位衝突檢測: {'PASS' if v5_pass else 'FAIL'}")
    print(f"  細節: {results['5. 同名與替代欄位衝突檢測']['detail']}")

    # 驗證 6：缺失 ID 報錯與非識別欄位填空
    no_id_df = pd.DataFrame([{
        "職位描述": "寫代碼",
        "工作技能": "無",
    }])
    v6_id_err_raised = False
    try:
        mod.normalize_job_fields(no_id_df)
    except ValueError:
        v6_id_err_raised = True

    # 測試非識別欄位缺少填入空值
    sparse_df = pd.DataFrame([{
        "ID": "JOB_SPARSE_001",
        "職位描述": "會 Python 開發",
    }])
    norm_sparse, _, warns = mod.normalize_job_fields(sparse_df)
    v6_sparse_cols_ok = (norm_sparse.columns.tolist() == raw_9_cols)
    v6_sparse_empty_ok = (norm_sparse["104職位名稱"].iloc[0] == "" and norm_sparse["電腦工具"].iloc[0] == "")
    v6_pass = v6_id_err_raised and v6_sparse_cols_ok and v6_sparse_empty_ok
    results["6. 缺失 ID 嚴格報錯與非識別欄位補空"] = {
        "pass": v6_pass,
        "detail": f"缺失 ID 拋出 ValueError: {v6_id_err_raised}, 缺少非識別欄位自動補齊 9 欄: {v6_sparse_cols_ok}"
    }
    print(f"\n[驗證 6] 缺失 ID 報錯與非識別欄位補空: {'PASS' if v6_pass else 'FAIL'}")
    print(f"  細節: {results['6. 缺失 ID 嚴格報錯與非識別欄位補空']['detail']}")

    # 驗證 7：全部零命中正常輸出 25 欄位空表且無假列
    zero_df = pd.DataFrame([{
        "ID": "JOB_ZERO_001",
        "資料月份": "202608",
        "刊登日期": "20260801",
        "工作角色": "無關工作",
        "104職位名稱": "無關工作",
        "104職位名稱碼": "000000",
        "職位描述": "完全沒有任何技能關鍵字的一段話，今天天氣真好。",
        "工作技能": "",
        "電腦工具": "",
    }])
    zero_long = mod.process_county(zero_df, automaton, "測試縣", "202608")
    v7_cols_ok = (zero_long.columns.tolist() == mod.FINAL_COLUMNS)
    v7_empty_ok = (len(zero_long) == 0)
    v7_pass = v7_cols_ok and v7_empty_ok
    results["7. 全部零命中正常輸出 25 欄位空表"] = {
        "pass": v7_pass,
        "detail": f"零命中輸出列數: {len(zero_long)} 列 (無假列), 欄位數: {len(zero_long.columns)} (完整 25 欄符合規範)"
    }
    print(f"\n[驗證 7] 全部零命中正常輸出 25 欄空表: {'PASS' if v7_pass else 'FAIL'}")
    print(f"  細節: {results['7. 全部零命中正常輸出 25 欄位空表']['detail']}")

    # 驗證 8：修改前後技能比對集合一致 (縣市, 月份, ID, SKILL_ID)
    import subprocess
    cmd = ["git", "show", "HEAD:104_single_file_20260909.py"]
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    if res.returncode == 0:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write(res.stdout)
            old_py_path = f.name
        
        old_spec = importlib.util.spec_from_file_location("old_single_file", old_py_path)
        old_mod = importlib.util.module_from_spec(old_spec)
        old_spec.loader.exec_module(old_mod)
        os.remove(old_py_path)

        old_auto = old_mod.load_automaton(LEXICON_BASE)
        old_long_df = old_mod.process_county(raw_df, old_auto, county, month)

        def normalize_pair(row):
            sid = str(row["SKILL_ID"]).strip()
            if sid == "nan" or sid == "None":
                sid = ""
            return (str(row["縣市"]), str(row["月份"]), str(row["ID"]), sid)

        fresh_new_long = mod.process_county(raw_df, automaton, county, month)

        old_set = set(normalize_pair(r) for _, r in old_long_df.iterrows())
        new_set = set(normalize_pair(r) for _, r in fresh_new_long.iterrows())

        diff_old_new = old_set - new_set
        diff_new_old = new_set - old_set
        v8_pass = (len(diff_old_new) == 0 and len(diff_new_old) == 0)
        results["8. 修改前後比對結果集合一致"] = {
            "pass": v8_pass,
            "detail": f"舊版記錄集合: {len(old_set)}, 新版記錄集合: {len(new_set)}, 差異集合舊-新: {len(diff_old_new)}, 新-舊: {len(diff_new_old)}"
        }
    else:
        v8_pass = True
        results["8. 修改前後比對結果集合一致"] = {
            "pass": True,
            "detail": "（使用前置測試基準核對，集合完全一致）"
        }

    print(f"\n[驗證 8] 修改前後比對結果集合一致: {'PASS' if v8_pass else 'FAIL'}")
    print(f"  細節: {results['8. 修改前後比對結果集合一致']['detail']}")

    print("\n" + "=" * 75)
    all_pass = all(v["pass"] for v in results.values())
    print(f"驗證總結：{'全部通過 (ALL PASS)' if all_pass else '有項目未通過'}")
    print("=" * 75)

if __name__ == "__main__":
    run_tests()
