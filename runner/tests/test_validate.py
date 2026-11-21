import yaml

from v6run.validate import validate


def test_valid_study_validates_cleanly(study_file):
    result = validate(str(study_file))
    assert result.ok
    assert result.problems == []
    assert result.study is not None


def test_invalid_params_are_all_reported(tmp_path, study_dict):
    study_dict["params"] = {"statistics": {"age": {"stats": ["not_a_real_statistic"]}}, "min_rows": -5}
    path = tmp_path / "study.yaml"
    path.write_text(yaml.safe_dump(study_dict))

    result = validate(str(path))

    assert not result.ok
    assert len(result.problems) >= 1


def test_malformed_study_file_is_reported_not_raised(tmp_path, study_dict):
    study_dict["version"] = "latest"
    path = tmp_path / "study.yaml"
    path.write_text(yaml.safe_dump(study_dict))

    result = validate(str(path))

    assert not result.ok
    assert any("latest" in p.lower() or "version" in p.lower() for p in result.problems)


def test_unknown_algorithm_is_reported_not_raised(tmp_path, study_dict):
    study_dict["algorithm"] = "does_not_exist"
    path = tmp_path / "study.yaml"
    path.write_text(yaml.safe_dump(study_dict))

    result = validate(str(path))

    assert not result.ok
    assert any("does_not_exist" in p for p in result.problems)
