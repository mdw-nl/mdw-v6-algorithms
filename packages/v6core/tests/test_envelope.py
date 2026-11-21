import numpy as np
import pandas as pd
from vantage6.algorithm.tools.mock_client import MockAlgorithmClient

from v6core.envelope import AlgorithmError, NodeError, node_envelope, safe_federated


def _mock_client(organization_id: int = 1) -> MockAlgorithmClient:
    client = MockAlgorithmClient(datasets=[[{"database": pd.DataFrame({"a": [1]})}]], module="os")
    client.organization_id = organization_id
    return client


def test_node_envelope_shape_and_jsonsafety():
    envelope = node_envelope(
        status="ok",
        organization_id=3,
        result={"mean": np.float64(1.5)},
        errors=[NodeError("MISSING_COLUMN", "column:age", "nope")],
    )
    assert envelope == {
        "envelope_version": 1,
        "status": "ok",
        "organization_id": 3,
        "result": {"mean": 1.5},
        "errors": [{"code": "MISSING_COLUMN", "scope": "column:age", "message": "nope"}],
    }
    assert isinstance(envelope["result"]["mean"], float)


def test_safe_federated_skips_provenance_for_mock_client():
    @safe_federated()
    def func(client):
        return {"ok": True}, []

    envelope = func(_mock_client(organization_id=7))
    assert envelope["status"] == "ok"
    assert envelope["organization_id"] == 7
    assert envelope["result"] == {"ok": True}


def test_safe_federated_reports_partial_status_with_scoped_errors():
    @safe_federated()
    def func(client):
        return {"age": {"mean": 10}}, [NodeError("NON_NUMERIC", "column:weight", "bad")]

    envelope = func(_mock_client())
    assert envelope["status"] == "partial"
    assert envelope["result"] == {"age": {"mean": 10}}
    assert envelope["errors"] == [{"code": "NON_NUMERIC", "scope": "column:weight", "message": "bad"}]


def test_safe_federated_full_failure_when_result_is_empty():
    @safe_federated()
    def func(client):
        return {}, [NodeError("EMPTY_AFTER_FILTER", "node", "no rows left")]

    envelope = func(_mock_client())
    assert envelope["status"] == "error"


def test_safe_federated_catches_algorithm_error():
    @safe_federated()
    def func(client):
        raise AlgorithmError("INVALID_PARAM", "node", "bad request")

    envelope = func(_mock_client())
    assert envelope["status"] == "error"
    assert envelope["errors"] == [{"code": "INVALID_PARAM", "scope": "node", "message": "bad request"}]


def test_safe_federated_scrubs_unexpected_exceptions():
    @safe_federated()
    def func(client):
        raise ValueError("value 42 is secret")

    envelope = func(_mock_client())
    assert envelope["status"] == "error"
    assert len(envelope["errors"]) == 1
    error = envelope["errors"][0]
    assert error["code"] == "INTERNAL_ERROR"
    assert "42" not in error["message"]
    assert "secret" not in error["message"]
