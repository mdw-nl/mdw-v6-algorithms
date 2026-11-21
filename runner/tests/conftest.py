from pathlib import Path

import pytest
import yaml


@pytest.fixture
def study_dict() -> dict:
    return {
        "profile": "dev",
        "collaboration": "demo",
        "initiating_org": "alpha",
        "algorithm": "descriptive_statistics",
        "version": "0.1.0",
        "organizations": ["alpha", "beta"],
        "params": {"statistics": {"age": {"stats": ["mean"]}}},
        "output": "results/descriptive_statistics",
    }


@pytest.fixture
def study_file(tmp_path: Path, study_dict: dict) -> Path:
    path = tmp_path / "study.yaml"
    path.write_text(yaml.safe_dump(study_dict))
    return path
