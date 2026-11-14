"""Hybrid Job Skill Extraction System."""

__all__ = ["JobSkillPipeline"]


def __getattr__(name: str):
    if name == "JobSkillPipeline":
        from src.pipeline import JobSkillPipeline
        return JobSkillPipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
