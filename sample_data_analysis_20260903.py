import pandas as pd
import re
import math
import os
import glob
import traceback

# ============================================================
# 0. Settings
# ============================================================

# 輸入資料夾:放置多個縣市的 wide.xlsx 檔案
INPUT_FOLDER = "/Users/anna/Desktop/Job_Description_fetch/AC 後檔案"

# 輸出資料夾:抽樣結果會依序輸出到這裡
OUTPUT_FOLDER = "/Users/anna/Library/CloudStorage/OneDrive-個人/ChenRA/AI_Job_project/許雁婷"

# 輸入檔案篩選規則(可依實際檔名調整,例如只抓 skills_ 開頭的檔案)
INPUT_PATTERN = "skills_*.xlsx"

# 輸出檔名前綴(原檔名前面加上這個前綴)
OUTPUT_PREFIX = "gold_label_"

RANDOM_STATE = 42  # 固定隨機種子，確保每次抽樣結果一致

# 固定樣本數(high / low / risky 三類為固定抽樣邏輯,不隨資料量變動)
N_HIGH = 30
N_LOW = 30
N_RISKY = 40

# 動態 Random Sample 設定
MIN_TOTAL_SAMPLE = 200      # 整體樣本數下限(不含被排除的重複)
SAMPLE_RATE = 0.10          # 依職缺總筆數抓取的百分比(10%)

TEXT_COLS = [
    "104職位名稱",
    "職位描述",
    "工作技能",
    "電腦工具"
]

RISKY_KEYWORDS = [
    "相",
    "電",
    "開發",
    "管理"
]

output_columns = [

    # ---------- Job ----------
    "ID",
    "104職位名稱",
    "職位描述",
    "工作技能",
    "電腦工具",

    # ---------- Sampling ----------
    "sample_type",

    # ---------- Machine Label ----------
    "技能數",
    "技能_中文",
    "認知技能",
    "社交技能",
    "特質技能",
    "財務技能",
    "管理技能",
    "數位技能",
    "技術技能",
    "電腦技能",
    "AI技能",
    "其他技能",

    # ---------- Human Label ----------
    "人工技能數",
    "人工技能_中文",
    "人工認知技能",
    "人工社交技能",
    "人工特質技能",
    "人工財務技能",
    "人工管理技能",
    "人工數位技能",
    "人工技術技能",
    "人工電腦技能",
    "人工AI技能",
    "人工其他技能",

    "人工備註"
]


# ============================================================
# 動態決定 Random Sample 數量
#
# 概念：
# 1. 依「該縣市職缺總筆數」x 10% 計算建議整體樣本數。
# 2. 整體樣本數（Random + High + Low + Risky）設下限 200 筆，
#    確保職缺量少的縣市仍有足夠樣本可供人工校對。
# 3. Random Sample 數量 = max(0, 整體樣本數 - 固定樣本數)。
#    若該縣市資料量過小，導致扣除固定樣本後所剩無幾，
#    後續抽樣仍會被 min(n, pool 大小) 保護，不會超抽。
# ============================================================

def calculate_dynamic_sample_size(population_size, sample_rate=SAMPLE_RATE):
    """依母體大小（population_size）x 固定比例（sample_rate）計算建議樣本數。"""

    if population_size <= 0:
        return 0

    return math.ceil(population_size * sample_rate)


# ============================================================
# 單一檔案處理流程
# ============================================================

def process_file(file_path, output_folder):
    """讀取單一縣市的 wide.xlsx,完成抽樣並輸出 gold label 檔案。"""

    file_name = os.path.basename(file_path)
    print("\n" + "=" * 60)
    print("處理檔案：", file_name)
    print("=" * 60)

    # ---------- 1. Read data ----------
    df = pd.read_excel(file_path)

    print("資料筆數：", len(df))

    # ---------- 1.5 動態決定 Random Sample 數量 ----------
    population_size = len(df)
    rate_based_n = calculate_dynamic_sample_size(population_size)

    dynamic_total_sample = max(rate_based_n, MIN_TOTAL_SAMPLE)
    dynamic_total_sample = min(dynamic_total_sample, population_size)

    n_random = max(0, dynamic_total_sample - (N_HIGH + N_LOW + N_RISKY))

    print("\n=== 動態 Random Sample 計算 ===")
    print("職缺總筆數：", population_size)
    print(f"比例計算樣本數（{int(SAMPLE_RATE * 100)}%）：", rate_based_n)
    print("整體樣本數下限：", MIN_TOTAL_SAMPLE)
    print("採用整體樣本數：", dynamic_total_sample)
    print("固定樣本數（high+low+risky）：", N_HIGH + N_LOW + N_RISKY)
    print("動態決定 N_RANDOM：", n_random)

    # ---------- 2. Clean 技能數 ----------
    df["技能數"] = pd.to_numeric(
        df["技能數"],
        errors="coerce"
    ).fillna(0)

    # ---------- 3. 建立 Machine Skill Density ----------
    q25 = df["技能數"].quantile(0.25)
    q75 = df["技能數"].quantile(0.75)

    print("\nQ25 =", q25)
    print("Q75 =", q75)

    # ---------- 4. High Skill Pool ----------
    high_pool = df[
        df["技能數"] >= q75
    ].copy()

    high_sample = high_pool.sample(
        n=min(N_HIGH, len(high_pool)),
        random_state=RANDOM_STATE
    )

    high_sample["sample_type"] = "high_machine_skill_count"

    # ---------- 5. Low Skill Pool ----------
    low_pool = df[
        (df["技能數"] <= q25) &
        (~df.index.isin(high_sample.index))
    ].copy()

    low_sample = low_pool.sample(
        n=min(N_LOW, len(low_pool)),
        random_state=RANDOM_STATE
    )

    low_sample["sample_type"] = "low_machine_skill_count"

    # ---------- 6. 建立全文 ----------
    df["combined_text"] = (
        df[TEXT_COLS]
        .fillna("")
        .astype(str)
        .agg(" ".join, axis=1)
    )

    # ---------- 7. Risky Keywords ----------
    pattern = "|".join(
        re.escape(keyword)
        for keyword in RISKY_KEYWORDS
    )

    already_selected = (
        high_sample.index
        .union(low_sample.index)
    )

    risky_pool = df[
        df["combined_text"].str.contains(
            pattern,
            regex=True,
            na=False
        )
        &
        (~df.index.isin(already_selected))
    ].copy()

    risky_sample = risky_pool.sample(
        n=min(N_RISKY, len(risky_pool)),
        random_state=RANDOM_STATE
    )

    risky_sample["sample_type"] = "risky_keyword"

    # ---------- 8. Random Sample ----------
    already_selected = (
        high_sample.index
        .union(low_sample.index)
        .union(risky_sample.index)
    )

    random_pool = df[
        ~df.index.isin(already_selected)
    ].copy()

    random_sample = random_pool.sample(
        n=min(n_random, len(random_pool)),
        random_state=RANDOM_STATE
    )

    random_sample["sample_type"] = "random"

    # ---------- 9. Combine ----------
    sample = pd.concat(
        [
            random_sample,
            high_sample,
            low_sample,
            risky_sample
        ],
        ignore_index=True
    )

    # ---------- 11. 建立 Human Label 欄位 ----------
    sample["人工技能數"] = ""
    sample["人工技能_中文"] = ""

    sample["人工認知技能"] = ""
    sample["人工社交技能"] = ""
    sample["人工特質技能"] = ""
    sample["人工財務技能"] = ""
    sample["人工管理技能"] = ""
    sample["人工數位技能"] = ""
    sample["人工技術技能"] = ""
    sample["人工電腦技能"] = ""
    sample["人工AI技能"] = ""
    sample["人工其他技能"] = ""

    sample["人工備註"] = ""

    # ---------- 12. Arrange columns ----------
    gold_label = sample[output_columns].copy()

    # ---------- 13. Export ----------
    os.makedirs(output_folder, exist_ok=True)

    output_file_name = OUTPUT_PREFIX + file_name
    output_path = os.path.join(output_folder, output_file_name)

    gold_label.to_excel(
        output_path,
        index=False
    )

    # ---------- 14. Check ----------
    print("\nSample distribution:")
    print(
        gold_label["sample_type"]
        .value_counts()
    )

    print("Total:", len(gold_label))
    print("Output:", output_path)

    return output_path, len(gold_label)


# ============================================================
# 主流程：批次處理輸入資料夾內所有 Excel 檔案
# ============================================================

def main():
    input_files = sorted(
        glob.glob(os.path.join(INPUT_FOLDER, INPUT_PATTERN))
    )

    print(f"在 {INPUT_FOLDER} 找到 {len(input_files)} 個檔案")

    results = []
    errors = []

    for file_path in input_files:
        try:
            output_path, n_rows = process_file(file_path, OUTPUT_FOLDER)
            results.append((os.path.basename(file_path), output_path, n_rows))
        except Exception as e:
            print(f"\n[錯誤] 處理 {file_path} 時失敗：{e}")
            traceback.print_exc()
            errors.append((file_path, str(e)))
            continue

    # ---------- 總結報告 ----------
    print("\n" + "=" * 60)
    print("批次處理完成")
    print("=" * 60)

    print(f"\n成功：{len(results)} 個檔案")
    for input_name, output_path, n_rows in results:
        print(f"  - {input_name} -> {output_path}（{n_rows} 筆）")

    if errors:
        print(f"\n失敗：{len(errors)} 個檔案")
        for file_path, err_msg in errors:
            print(f"  - {file_path}: {err_msg}")


if __name__ == "__main__":
    main()