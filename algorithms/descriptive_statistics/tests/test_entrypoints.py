"""Integration tests through the vantage6 mock network (AGENTS.md §10).

These exercise `central()` end to end: envelope assembly, participation, quorum,
and fault injection -- everything `test_core.py` can't reach because it calls
`core.py` directly. The mock client runs every org's `compute_local_stats` call
in-process and synchronously (see `vantage6.algorithm.tools.mock_client`), so these
run fast with no real network.
"""

import pandas as pd
import pytest
from vantage6.algorithm.tools.mock_client import MockAlgorithmClient

import descriptive_statistics as algorithm


def _mock_client(dataframes: list[pd.DataFrame]) -> MockAlgorithmClient:
    datasets = [[{"database": df}] for df in dataframes]
    return MockAlgorithmClient(datasets=datasets, module="descriptive_statistics")


def _central(client: MockAlgorithmClient, **kwargs) -> dict:
    return algorithm.central(mock_client=client, **kwargs)


@pytest.fixture
def three_healthy_shards(healthy_df) -> list[pd.DataFrame]:
    size = len(healthy_df) // 3
    return [healthy_df.iloc[:size], healthy_df.iloc[size : 2 * size], healthy_df.iloc[2 * size :]]


class TestHappyPath:
    def test_ok_status_and_exact_aggregation(self, three_healthy_shards, healthy_df):
        client = _mock_client(three_healthy_shards)
        result = _central(client, statistics={"age": {"stats": ["mean", "nrows"]}})

        assert result["status"] == "ok"
        assert result["result"]["columns"]["age"]["mean"] == pytest.approx(healthy_df["age"].mean(), abs=1e-9)
        assert result["result"]["columns"]["age"]["nrows"] == {"value": len(healthy_df)}
        assert len(result["participation"]) == 3
        assert all(p["status"] == "included" for p in result["participation"])
        assert result["algorithm"]["name"] == "descriptive_statistics"
        assert result["errors"] == []

    def test_envelope_is_json_safe(self, three_healthy_shards):
        import json

        client = _mock_client(three_healthy_shards)
        result = _central(client, statistics={"age": {"stats": ["mean", "minmax"]}})
        json.dumps(result)  # must not raise


class TestFaultInjection:
    """AGENTS.md §10.3: one bad node must not fail the whole run."""

    def test_one_node_missing_a_column_is_partial_not_a_crash(self, healthy_df, broken_df):
        # broken_df has no 'site' column; healthy_df does.
        client = _mock_client([healthy_df, broken_df])
        result = _central(client, statistics={"site": {"stats": ["counts"]}})

        assert result["status"] in ("partial", "ok")
        assert result["result"]["columns"]["site"]["counts"]  # alpha/beta/gamma still aggregated
        assert any("site" in w for w in result["warnings"])

    def test_node_below_min_rows_is_excluded_not_fatal(self, healthy_df, small_df):
        client = _mock_client([healthy_df, small_df])
        result = _central(client, statistics={"age": {"stats": ["mean"]}}, min_rows=5)

        statuses = {p["organization"]: p["status"] for p in result["participation"]}
        assert any(status == "failed" for status in statuses.values())
        assert any(
            p["status"] == "failed" and p["reason"] == "BELOW_MIN_ROWS" for p in result["participation"]
        )
        assert result["result"]["columns"]["age"]["mean"] is not None

    def test_quorum_not_met_is_a_clean_error_not_an_exception(self, small_df):
        client = _mock_client([small_df])
        result = _central(client, statistics={"age": {"stats": ["mean"]}}, min_rows=5, min_organizations=1)

        assert result["status"] == "error"
        assert result["errors"][0]["code"] == "QUORUM_NOT_MET"

    def test_invalid_param_is_a_clean_error_naming_every_problem(self, healthy_df):
        client = _mock_client([healthy_df])
        result = _central(client, statistics={"age": {"stats": ["not_a_real_statistic"]}})

        assert result["status"] == "error"
        assert result["errors"][0]["code"] == "INVALID_PARAM"

    def test_unknown_organization_name_is_a_clean_error(self, healthy_df):
        client = _mock_client([healthy_df])
        result = _central(client, statistics={"age": {"stats": ["mean"]}}, organizations=["does-not-exist"])

        assert result["status"] == "error"
        assert result["errors"][0]["code"] == "INVALID_PARAM"


class TestProvenanceGuard:
    def test_compute_local_stats_cannot_be_called_directly_on_a_real_client(self, healthy_df):
        # A client with no access token mimics a real (non-mock) AlgorithmClient that
        # the provenance guard can't verify has a parent task -- it must fail closed
        # rather than silently trusting it (v6core.provenance only exempts the mock
        # client itself, never a client that merely isn't a MockAlgorithmClient).
        class _FakeTokenClient:
            _access_token = None
            organization_id = 1

        envelope = algorithm.compute_local_stats(
            mock_data=[healthy_df],
            mock_client=_FakeTokenClient(),
            statistics={
                "age": {"stats": ["mean"], "bins": None, "min_cap": None, "max_cap": None, "inliers": None}
            },
            filters=None,
            min_cell_count=5,
            max_categories=20,
        )
        assert envelope["status"] == "error"
        assert envelope["errors"][0]["code"] == "NOT_SUBTASK"
