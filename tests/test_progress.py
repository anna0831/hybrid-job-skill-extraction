import time
import pytest
import pandas as pd
from src.utils.progress import ProgressTracker, ProgressSnapshot, format_time
from src.hybrid_pipeline import HybridJobSkillPipeline


def test_format_time():
    """驗證時間格式化輔助函數。"""
    assert format_time(None) == "正在估算..."
    assert format_time(0) == "00:00"
    assert format_time(-5) == "00:00"
    assert format_time(45) == "00:45"
    assert format_time(125) == "02:05"
    assert format_time(3665) == "01:01:05"


def test_processed_zero_warmup():
    """測試案例 1: processed = 0 時，處於暖機狀態且 ETA 顯示正在估算。"""
    tracker = ProgressTracker(warmup_min_jobs=10)
    tracker.start(total=100)
    snap = tracker.update(processed=0, stage="AC Matching", force=True)

    assert snap is not None
    assert snap.processed == 0
    assert snap.total == 100
    assert snap.percent == 0.0
    assert snap.is_warmup is True
    assert snap.eta_seconds is None
    assert snap.formatted_eta == "正在估算..."
    assert snap.is_completed is False


def test_progress_percentage():
    """測試案例 2: 50 / 100 處理時，進度精確為 50.0%。"""
    tracker = ProgressTracker(warmup_min_jobs=10)
    tracker.start(total=100)
    snap = tracker.update(processed=50, stage="AC Matching", force=True)

    assert snap is not None
    assert snap.processed == 50
    assert snap.total == 100
    assert snap.percent == 50.0


def test_processing_speed_calculation():
    """測試案例 3: 處理速度計算 (jobs_per_second)。"""
    tracker = ProgressTracker(warmup_min_jobs=5)
    tracker.start(total=100)
    # 模擬 2 秒處理 20 筆
    tracker.start_time = time.time() - 2.0
    snap = tracker.update(processed=20, stage="AC Matching", force=True)

    assert snap is not None
    assert snap.jobs_per_second >= 9.0 and snap.jobs_per_second <= 11.0
    assert "jobs/sec" in snap.formatted_speed


def test_eta_calculation_and_ema():
    """測試案例 4: 平滑 ETA 計算與指數移動平均。"""
    tracker = ProgressTracker(alpha=0.2, warmup_min_jobs=5, warmup_ratio=0.01)
    tracker.start(total=100)
    tracker.start_time = time.time() - 10.0

    # 模擬 20 筆處理，每筆 0.5 秒
    for p in range(1, 21):
        tracker.update(processed=p, job_latency_sec=0.5, force=False)

    snap = tracker.update(processed=20, force=True)
    assert snap is not None
    assert snap.is_warmup is False
    assert snap.eta_seconds is not None
    # 剩餘 80 筆 * ~0.5 秒 = ~40 秒
    assert 35.0 <= snap.eta_seconds <= 45.0
    assert "約 " in snap.formatted_eta


def test_completed_job_eta_zero():
    """測試案例 5: 處理完成時，ETA 歸零且 is_completed = True。"""
    tracker = ProgressTracker()
    tracker.start(total=100)
    tracker.update(processed=50, force=True)

    snap = tracker.finish()
    assert snap.is_completed is True
    assert snap.processed == 100
    assert snap.percent == 100.0
    assert snap.eta_seconds == 0.0
    assert snap.formatted_eta == "00:00"


def test_invalid_total_zero():
    """測試案例 6: 總筆數為 0 時的邊界防禦。"""
    tracker = ProgressTracker()
    tracker.start(total=0)
    snap = tracker.update(processed=0, force=True)

    assert snap is not None
    assert snap.total == 0
    assert snap.percent == 0.0
    assert snap.eta_seconds is None
    assert snap.formatted_eta == "正在估算..."


def test_callback_receives_correct_metadata():
    """測試案例 7: 回呼函式能精準接收 processed/total 與階段資訊。"""
    received = []

    def dummy_callback(snapshot: ProgressSnapshot):
        received.append((snapshot.processed, snapshot.total, snapshot.stage))

    pipeline = HybridJobSkillPipeline(
        lexicon_path="lexicon/sample/mini_skill_lexicon.csv",
        verifier_provider="mock",
        grounder_provider="mock",
        enable_fn_recovery=False,
    )

    df_sample = pd.DataFrame([
        {"id": "J1", "job_title": "Python 工程師", "job_desc": "負責後端開發"},
        {"id": "J2", "job_title": "會計", "job_desc": "審核傳票與立帳"},
    ])

    pipeline.process_dataframe(df_sample, progress_callback=dummy_callback)

    assert len(received) >= 3
    # 初始快照
    assert received[0][0] == 0
    assert received[0][1] == 2
    # 最終快照
    assert received[-1][0] == 2
    assert received[-1][1] == 2
    assert received[-1][2] == ProgressTracker.STAGE_COMPLETED


def test_progress_callback_does_not_alter_results():
    """測試案例 8: 啟用進度回呼與未啟用回呼的擷取產出完全等價。"""
    pipeline = HybridJobSkillPipeline(
        lexicon_path="lexicon/sample/mini_skill_lexicon.csv",
        verifier_provider="mock",
        grounder_provider="mock",
        enable_fn_recovery=True,
    )

    df_test = pd.DataFrame([
        {
            "id": "J_001",
            "job_title": "Python 後端工程師",
            "job_desc": "負責後端 API 開發與架構規劃，需熟悉 Python 與 SQL。",
            "tools": "Python, Docker",
            "job_skills": "Python, SQL",
        },
        {
            "id": "J_002",
            "job_title": "塑膠射出機台操作員",
            "job_desc": "產線機台操作、日常設備保養。工作環境每日需保持整潔清潔。",
            "tools": "車床",
            "job_skills": "機台操作",
        },
    ])

    # 1. 無回呼執行
    long_a, wide_a, stats_a = pipeline.process_dataframe(df_test, county="南投縣", month="2026-09")

    # 2. 有回呼執行 (重設 router 累計統計以確保環境乾淨一致)
    pipeline.router.reset_stats()
    snaps = []
    long_b, wide_b, stats_b = pipeline.process_dataframe(
        df_test,
        county="南投縣",
        month="2026-09",
        progress_callback=lambda s: snaps.append(s),
    )

    # 驗證輸出 DataFrame 完全相等
    pd.testing.assert_frame_equal(long_a, long_b)
    pd.testing.assert_frame_equal(wide_a, wide_b)
    assert stats_a == stats_b
    assert len(snaps) > 0
