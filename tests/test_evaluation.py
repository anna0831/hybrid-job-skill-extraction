"""Tests for evaluation metrics, slicing, and benchmark evaluation pipeline."""

import pytest
from src.evaluation.metrics import compute_metrics
from src.evaluation.slicer import slice_metrics_by_field, slice_metrics_by_skill_category
from src.evaluation.evaluator import PipelineEvaluator
from src.pipeline import JobSkillPipeline


def test_compute_metrics_exact():
    y_true = [{"A", "B"}, {"C"}]
    y_pred = [{"A", "B"}, {"C"}]
    metrics = compute_metrics(y_true, y_pred, total_time_ms=10.0)

    assert metrics.tp == 3
    assert metrics.fp == 0
    assert metrics.fn == 0
    assert metrics.precision == 1.0
    assert metrics.recall == 1.0
    assert metrics.f1 == 1.0
    assert metrics.false_positive_rate == 0.0
    assert metrics.false_negative_rate == 0.0


def test_compute_metrics_with_fp_fn():
    # Job 1: True={A, B}, Pred={A, C} -> TP=1 (A), FP=1 (C), FN=1 (B)
    # Job 2: True={D}, Pred={D, E}    -> TP=1 (D), FP=1 (E), FN=0
    # Total: TP=2, FP=2, FN=1
    y_true = [{"A", "B"}, {"D"}]
    y_pred = [{"A", "C"}, {"D", "E"}]
    metrics = compute_metrics(y_true, y_pred)

    assert metrics.tp == 2
    assert metrics.fp == 2
    assert metrics.fn == 1
    # Micro Precision = 2 / (2 + 2) = 0.5
    assert metrics.precision == 0.5
    # Micro Recall = 2 / (2 + 1) = 0.6667
    assert pytest.approx(metrics.recall, 0.001) == 0.6667
    assert metrics.false_positive_rate == 0.5


def test_slice_metrics_by_field():
    dataset = [
        {"id": "1", "county": "台北"},
        {"id": "2", "county": "台中"},
    ]
    y_true = [{"A"}, {"B"}]
    y_pred = [{"A"}, {"C"}]

    slices = slice_metrics_by_field(dataset, y_true, y_pred, "county")
    assert "台北" in slices
    assert "台中" in slices
    assert slices["台北"].f1 == 1.0
    assert slices["台中"].f1 == 0.0


def test_pipeline_evaluator_runs_on_benchmark():
    evaluator = PipelineEvaluator("data/gold_labels/sample_benchmark.jsonl")
    pipeline = JobSkillPipeline("lexicon/sample/mini_skill_lexicon.csv")
    report = evaluator.evaluate(pipeline, pipeline_name="Test Baseline AC")

    assert report.overall.total_samples == len(evaluator.dataset)
    assert report.overall.precision > 0.0
    assert report.overall.recall > 0.0
    assert "risky_keyword" in report.by_sample_type
    assert len(report.error_samples) > 0  # Should detect known false positive/negative cases!
