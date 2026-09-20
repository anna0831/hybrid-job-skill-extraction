"""進度追蹤與剩餘時間 (ETA) 估算模組。

提供基於真實處理筆數、平滑化指數移動平均 (EMA) 與時間節流之即時進度追蹤，
嚴格落實 $0 成本政策、無造假計時器與純觀察者架構（不干預任何技能擷取邏輯）。
"""

import time
import math
from typing import Optional, Callable, Dict, Any
from pydantic import BaseModel, Field


def format_time(seconds: Optional[float]) -> str:
    """將秒數格式化為 MM:SS 或 HH:MM:SS 字串。"""
    if seconds is None:
        return "正在估算..."
    if seconds <= 0:
        return "00:00"
    
    total_sec = int(math.ceil(seconds))
    hours = total_sec // 3600
    minutes = (total_sec % 3600) // 60
    secs = total_sec % 60
    
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


class ProgressSnapshot(BaseModel):
    """進度快照資料模型。"""
    processed: int = Field(default=0, description="已處理職缺數量")
    total: int = Field(default=0, description="總職缺數量")
    stage: str = Field(default="", description="目前執行階段名稱")
    elapsed_seconds: float = Field(default=0.0, description="已耗費秒數")
    jobs_per_second: float = Field(default=0.0, description="每秒處理職缺數 (Throughput)")
    eta_seconds: Optional[float] = Field(default=None, description="預估剩餘秒數")
    is_warmup: bool = Field(default=True, description="是否仍處於暖機估算階段")
    is_completed: bool = Field(default=False, description="是否已全部處理完成")
    error_message: Optional[str] = Field(default=None, description="錯誤訊息 (若失敗)")

    @property
    def percent(self) -> float:
        """百分比 (0.0 ~ 100.0)。"""
        if self.total <= 0:
            return 0.0
        return min(100.0, round((self.processed / self.total) * 100.0, 1))

    @property
    def formatted_elapsed(self) -> str:
        return format_time(self.elapsed_seconds)

    @property
    def formatted_eta(self) -> str:
        if self.is_completed:
            return "00:00"
        if self.is_warmup or self.eta_seconds is None:
            return "正在估算..."
        return f"約 {format_time(self.eta_seconds)}"

    @property
    def formatted_speed(self) -> str:
        return f"{self.jobs_per_second:.1f} jobs/sec"


class ProgressTracker:
    """真實進度追蹤與平滑 ETA 估算器。
    
    特性：
    1. 真實計數：基於實際處理職缺數計算百分比，絕無隨機假數。
    2. EMA 平滑：單筆耗時使用指數移動平均，避免長文字職缺導致 ETA 劇烈震盪。
    3. 暖機防抖：前 10 筆或前 2% 顯示「正在估算...」，避免初始數值失真。
    4. 節流渲染：預設 0.25 秒間隔觸發更新，將 UI 渲染開銷壓制在 5% 以下。
    """

    # 階段名稱標準常數 (供前後端統一引用)
    STAGE_PREPARING = "準備資料"
    STAGE_AC_MATCHING = "AC Matching"
    STAGE_RISK_ROUTING = "Risk Routing"
    STAGE_CONTEXT_VERIFY = "Context Verification"
    STAGE_RESIDUAL_RECOVERY = "Residual Recovery"
    STAGE_AGGREGATING = "Wide Table Aggregation"
    STAGE_COMPLETED = "處理完成"
    STAGE_FAILED = "處理失敗"

    def __init__(
        self,
        alpha: float = 0.2,
        throttle_interval_sec: float = 0.25,
        warmup_min_jobs: int = 10,
        warmup_ratio: float = 0.02,
    ):
        """
        Args:
            alpha: EMA 平滑係數 (0.0 < alpha <= 1.0，值越小越平滑，預設 0.2)
            throttle_interval_sec: 回傳/通知節流間隔 (秒)
            warmup_min_jobs: 暖機最小筆數門檻 (預設 10)
            warmup_ratio: 暖機比例門檻 (預設 2%)
        """
        self.alpha = max(0.01, min(1.0, alpha))
        self.throttle_interval_sec = throttle_interval_sec
        self.warmup_min_jobs = warmup_min_jobs
        self.warmup_ratio = warmup_ratio

        self.total: int = 0
        self.processed: int = 0
        self.stage: str = self.STAGE_PREPARING
        self.start_time: float = 0.0
        self.last_update_time: float = 0.0
        self.last_job_time: float = 0.0
        self.ema_job_time: Optional[float] = None
        self.is_completed: bool = False
        self.error_message: Optional[str] = None

    def start(self, total: int, initial_stage: str = STAGE_AC_MATCHING):
        """啟動進度追蹤。"""
        self.total = max(0, total)
        self.processed = 0
        self.stage = initial_stage
        self.start_time = time.time()
        self.last_update_time = self.start_time
        self.last_job_time = self.start_time
        self.ema_job_time = None
        self.is_completed = False
        self.error_message = None

    def update(
        self,
        processed: int,
        stage: Optional[str] = None,
        job_latency_sec: Optional[float] = None,
        force: bool = False,
    ) -> Optional[ProgressSnapshot]:
        """記錄單一或批次職缺進度。
        
        Args:
            processed: 目前已處理的總職缺筆數
            stage: 目前執行階段名稱
            job_latency_sec: 最近單筆耗時 (秒)，若為 None 則以當前時間與上次更新時間計算
            force: 是否忽略節流強制產出快照 (通常用於完成或最後一筆)
            
        Returns:
            符合節流週期或 force 時回傳 ProgressSnapshot，否則回傳 None
        """
        now = time.time()
        new_processed = max(0, min(self.total, processed)) if self.total > 0 else processed
        delta_jobs = new_processed - self.processed
        self.processed = new_processed
        if stage:
            self.stage = stage

        # 計算單筆耗時與更新 EMA (僅當有新處理職缺時更新，避免同筆重複呼叫時零耗時干擾)
        if delta_jobs > 0:
            if job_latency_sec is not None and job_latency_sec > 0:
                single_job_time = job_latency_sec / delta_jobs
            else:
                time_since_last_job = now - self.last_job_time
                single_job_time = max(0.0001, time_since_last_job / delta_jobs)
            self.last_job_time = now

            if self.ema_job_time is None:
                self.ema_job_time = single_job_time
            else:
                self.ema_job_time = (self.alpha * single_job_time) + ((1.0 - self.alpha) * self.ema_job_time)

        # 檢查是否到達節流更新時間或已完成
        time_since_last_update = now - self.last_update_time
        is_done = (self.total > 0 and self.processed >= self.total)

        if not force and not is_done and time_since_last_update < self.throttle_interval_sec:
            return None

        self.last_update_time = now
        return self._create_snapshot(now=now, is_completed=is_done)

    def finish(self, stage: str = STAGE_COMPLETED) -> ProgressSnapshot:
        """標記處理完成，強制回傳 100% 快照與歸零之 ETA。"""
        now = time.time()
        self.processed = self.total
        self.stage = stage
        self.is_completed = True
        return self._create_snapshot(now=now, is_completed=True)

    def fail(self, stage: str = STAGE_FAILED, error: str = "") -> ProgressSnapshot:
        """標記處理失敗，保留現場數據與錯誤訊息。"""
        now = time.time()
        self.stage = stage
        self.error_message = error
        self.is_completed = False
        return self._create_snapshot(now=now, is_completed=False)

    def _create_snapshot(self, now: float, is_completed: bool) -> ProgressSnapshot:
        """構建快照物件。"""
        elapsed = max(0.001, now - self.start_time) if self.start_time > 0 else 0.0
        jobs_per_sec = (self.processed / elapsed) if elapsed > 0 and self.processed > 0 else 0.0

        # 判斷是否處於暖機期
        warmup_threshold = max(self.warmup_min_jobs, int(self.total * self.warmup_ratio))
        is_warmup = (self.processed < warmup_threshold) and not is_completed

        # 計算 ETA
        eta_seconds: Optional[float] = None
        if is_completed:
            eta_seconds = 0.0
        elif not is_warmup and self.processed > 0 and self.total > self.processed:
            remaining = self.total - self.processed
            # 優先採用平滑後的 EMA 估計，若無則採用整體平均
            unit_time = self.ema_job_time if self.ema_job_time and self.ema_job_time > 0 else (elapsed / self.processed)
            eta_seconds = max(0.0, unit_time * remaining)

        return ProgressSnapshot(
            processed=self.processed,
            total=self.total,
            stage=self.stage,
            elapsed_seconds=round(elapsed, 2),
            jobs_per_second=round(jobs_per_sec, 2),
            eta_seconds=round(eta_seconds, 1) if eta_seconds is not None else None,
            is_warmup=is_warmup,
            is_completed=is_completed,
            error_message=self.error_message,
        )
