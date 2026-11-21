import json
from unittest.mock import patch

import pytest

from v6run.runstudy import RunnerError, _lookup_id, _wait_for_task, run


def test_lookup_id_finds_match():
    items = [{"id": 1, "name": "alpha"}, {"id": 2, "name": "beta"}]
    assert _lookup_id(items, "beta", "Organization") == 2


def test_lookup_id_raises_clear_error_when_missing():
    items = [{"id": 1, "name": "alpha"}]
    with pytest.raises(RunnerError, match="alpha"):
        _lookup_id(items, "does-not-exist", "Organization")


class _FakeClient:
    def __init__(self, status_sequence):
        self._status_sequence = list(status_sequence)
        self.requested_paths = []

    def request(self, path):
        self.requested_paths.append(path)
        status = self._status_sequence.pop(0) if len(self._status_sequence) > 1 else self._status_sequence[0]
        return {"status": status}


def test_wait_for_task_returns_on_first_completed_status():
    client = _FakeClient(["completed"])
    status = _wait_for_task(client, task_id=1, timeout_s=5)
    assert status == "completed"


def test_wait_for_task_times_out_on_a_stuck_task():
    client = _FakeClient(["pending"])
    with pytest.raises(RunnerError, match="did not finish"):
        _wait_for_task(client, task_id=1, timeout_s=0.05)


class _FakeSubClient:
    def __init__(self, data):
        self._data = data

    def list(self):
        return {"data": self._data}


class _FakeTaskClient:
    def __init__(self, task_id):
        self._task_id = task_id
        self.created_with = None

    def create(self, **kwargs):
        self.created_with = kwargs
        return {"id": self._task_id}


class _FakeResultClient:
    def __init__(self, envelope):
        self._envelope = envelope

    def from_task(self, task_id):
        return {"data": [{"result": json.dumps(self._envelope)}]}


class _FakeRunClient:
    def __init__(self):
        self.status_requests = 0

    def request(self, path):
        self.status_requests += 1
        return {"status": "completed"}


class _FakeVantage6Client:
    def __init__(self, *args, **kwargs):
        self.organization = _FakeSubClient([{"id": 10, "name": "alpha"}, {"id": 20, "name": "beta"}])
        self.collaboration = _FakeSubClient([{"id": 1, "name": "demo"}])
        self.task = _FakeTaskClient(task_id=99)
        envelope = {
            "status": "ok",
            "algorithm": {"name": "descriptive_statistics", "version": "0.1.0", "v6core_version": "0.1.0"},
            "params": {},
            "participation": [{"organization": "alpha", "status": "included"}],
            "result": {"columns": {"age": {"mean": 42.0}}},
            "warnings": [],
            "errors": [],
            "privacy": {"thresholds": {}},
        }
        self.result = _FakeResultClient(envelope)
        self.authenticated_with = None
        self._status_calls = 0

    def authenticate(self, username, password):
        self.authenticated_with = (username, password)

    def setup_encryption(self, key):
        pass

    def setup_collaboration(self, collaboration_id):
        self.collaboration_id = collaboration_id

    def request(self, path):
        self._status_calls += 1
        return {"status": "completed"}


def test_run_end_to_end_against_a_fake_server(study_file, tmp_path):
    out_dir = tmp_path / "out"
    with patch("v6run.runstudy.Client", _FakeVantage6Client):
        result = run(str(study_file), out_dir=str(out_dir))

    assert result.task_id == 99
    assert result.envelope["status"] == "ok"
    assert (out_dir / "result.json").exists()
    assert (out_dir / "params.json").exists()
    assert (out_dir / "summary.md").exists()

    written_envelope = json.loads((out_dir / "result.json").read_text())
    assert written_envelope["result"]["columns"]["age"]["mean"] == 42.0


def test_run_raises_runner_error_for_invalid_study(tmp_path, study_dict):
    import yaml

    study_dict["version"] = "latest"
    path = tmp_path / "study.yaml"
    path.write_text(yaml.safe_dump(study_dict))

    with pytest.raises(RunnerError):
        run(str(path))


def test_run_raises_runner_error_for_unknown_organization(study_dict, tmp_path):
    import yaml

    study_dict["initiating_org"] = "does-not-exist"
    path = tmp_path / "study.yaml"
    path.write_text(yaml.safe_dump(study_dict))

    with patch("v6run.runstudy.Client", _FakeVantage6Client):
        with pytest.raises(RunnerError, match="does-not-exist"):
            run(str(path))
