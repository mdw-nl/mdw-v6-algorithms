import jwt
import pandas as pd
import pytest
from vantage6.algorithm.tools.mock_client import MockAlgorithmClient

from v6core.provenance import ProvenanceError, ensure_spawned_by_central


class _FakeTaskClient:
    def __init__(self, task: dict):
        self._task = task

    def create(self, input_: dict, organizations: list[int], name="subtask", description=None) -> dict:
        raise AssertionError("not used in these tests")

    def get(self, task_id: int) -> dict:
        return self._task


class _BrokenTaskClient:
    def create(self, input_: dict, organizations: list[int], name="subtask", description=None) -> dict:
        raise AssertionError("not used in these tests")

    def get(self, task_id: int) -> dict:
        raise RuntimeError("server unreachable")


class _UnusedRunClient:
    """Provenance tests never reach `client.run` -- this just satisfies the shape."""

    def from_task(self, task_id: int) -> list[dict]:
        raise AssertionError("not used in these tests")


class _UnusedResultClient:
    """Provenance tests never reach `client.result` -- this just satisfies the shape."""

    def get(self, result_id: int):
        raise AssertionError("not used in these tests")


class _FakeClient:
    def __init__(self, *, access_token: str | None, task: dict, task_client=None):
        self._access_token = access_token
        self.task = task_client if task_client is not None else _FakeTaskClient(task)
        self.organization_id = 1
        self.run = _UnusedRunClient()
        self.result = _UnusedResultClient()


def _token(payload: dict) -> str:
    return jwt.encode({"sub": payload}, "secret", algorithm="HS256")


def test_mock_client_is_exempt():
    mock_client = MockAlgorithmClient(datasets=[[{"database": pd.DataFrame({"a": [1]})}]], module="os")
    ensure_spawned_by_central(mock_client)  # no raise


def test_raises_when_token_missing():
    client = _FakeClient(access_token=None, task={"parent": 1})
    with pytest.raises(ProvenanceError):
        ensure_spawned_by_central(client)


def test_raises_when_task_has_no_parent():
    token = _token({"task_id": 42})
    client = _FakeClient(access_token=token, task={"id": 42, "parent": None})
    with pytest.raises(ProvenanceError):
        ensure_spawned_by_central(client)


def test_passes_when_task_has_parent():
    token = _token({"task_id": 42})
    client = _FakeClient(access_token=token, task={"id": 42, "parent": {"id": 7}})
    ensure_spawned_by_central(client)  # no raise


def test_raises_when_task_lookup_fails():
    client = _FakeClient(access_token=_token({"task_id": 1}), task={}, task_client=_BrokenTaskClient())
    with pytest.raises(ProvenanceError):
        ensure_spawned_by_central(client)
