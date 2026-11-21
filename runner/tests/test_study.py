import pytest
from pydantic import ValidationError

from v6run.study import Study, load_study


def test_load_study_parses_valid_file(study_file):
    study = load_study(study_file)
    assert study.algorithm == "descriptive_statistics"
    assert study.organizations == ["alpha", "beta"]


def test_rejects_latest_as_version(study_dict):
    study_dict["version"] = "latest"
    with pytest.raises(ValidationError):
        Study.model_validate(study_dict)


def test_rejects_unknown_fields(study_dict):
    study_dict["typo_field"] = "oops"
    with pytest.raises(ValidationError):
        Study.model_validate(study_dict)


def test_missing_file_raises(tmp_path):
    with pytest.raises(OSError):
        load_study(tmp_path / "does-not-exist.yaml")


def test_non_mapping_yaml_raises(tmp_path):
    path = tmp_path / "study.yaml"
    path.write_text("- just\n- a\n- list\n")
    with pytest.raises(ValueError):
        load_study(path)
