import numpy as np
import pandas as pd
import pytest

from descriptive_statistics import core
from v6core.envelope import AlgorithmError

MIN_CELL_COUNT = 5
MAX_CATEGORIES = 20


def _spec(stats: list[str], **extra) -> dict:
    return {"stats": stats, "bins": None, "min_cap": None, "max_cap": None, "inliers": None, **extra}


def _run_federated(shards: list[pd.DataFrame], statistics: dict) -> dict:
    """Split `df` into `shards`, run `local_statistics` per shard, aggregate centrally."""
    local_results = [
        core.local_statistics(
            shard, statistics, filters=None, min_cell_count=MIN_CELL_COUNT, max_categories=MAX_CATEGORIES
        )[0]
        for shard in shards
    ]
    columns, warnings = core.aggregate_statistics(local_results, statistics)
    return {"columns": columns, "warnings": warnings}


def _shard(df: pd.DataFrame, n: int) -> list[pd.DataFrame]:
    size = -(-len(df) // n)  # ceil division, so n shards always covers every row
    return [df.iloc[i : i + size] for i in range(0, len(df), size)]


class TestFederatedEqualsPooled:
    """AGENTS.md §10.1: federated must equal pooled, tight tolerances."""

    def test_mean_and_std_match_pooled_exactly(self, healthy_df):
        statistics = {"age": _spec(["mean", "std", "nrows"])}
        federated = _run_federated(_shard(healthy_df, 4), statistics)["columns"]["age"]

        pooled_mean = healthy_df["age"].mean()
        pooled_std = healthy_df["age"].std(ddof=1)

        assert federated["mean"] == pytest.approx(pooled_mean, abs=1e-9)
        assert federated["std"] == pytest.approx(pooled_std, abs=1e-9)
        assert federated["nrows"] == {"value": len(healthy_df)}

    def test_counts_match_pooled_exactly(self, healthy_df):
        statistics = {"sex": _spec(["counts"])}
        federated = _run_federated(_shard(healthy_df, 3), statistics)["columns"]["sex"]["counts"]

        pooled_counts = healthy_df["sex"].value_counts()
        for label, count in pooled_counts.items():
            assert federated[str(label)] == {"lower": int(count), "upper": int(count)}

    def test_minmax_matches_pooled_when_capped(self, healthy_df):
        statistics = {"age": _spec(["minmax"], min_cap=0, max_cap=120)}
        federated = _run_federated(_shard(healthy_df, 5), statistics)["columns"]["age"]

        assert federated["minmax"] == {
            "min": float(healthy_df["age"].min()),
            "max": float(healthy_df["age"].max()),
        }

    def test_binned_counts_match_pooled_histogram(self, healthy_df):
        bins = [0, 30, 60, 200]
        statistics = {"age": _spec(["binned_counts"], bins=bins)}
        federated = _run_federated(_shard(healthy_df, 4), statistics)["columns"]["age"]["binned_counts"]

        pooled_counts, _ = np.histogram(healthy_df["age"].to_numpy(), bins=bins)
        assert sorted(b["lower"] for b in federated.values()) == sorted(int(c) for c in pooled_counts)


class TestPrivacy:
    def test_minmax_without_caps_is_rounded_not_exact(self, healthy_df):
        statistics = {"age": _spec(["minmax"])}
        federated = _run_federated([healthy_df], statistics)["columns"]["age"]["minmax"]

        exact_min, exact_max = float(healthy_df["age"].min()), float(healthy_df["age"].max())
        assert federated["min"] == core._round_sig(exact_min, core.DEFAULT_MINMAX_SIG_FIGS)
        assert federated["max"] == core._round_sig(exact_max, core.DEFAULT_MINMAX_SIG_FIGS)

    def test_small_count_is_merged_into_other(self):
        df = pd.DataFrame({"flag": ["A"] * 3 + ["B"] * 20})
        statistics = {"flag": _spec(["counts"])}
        result = _run_federated([df], statistics)["columns"]["flag"]["counts"]

        # Below min_cell_count: never shown under its own label, not even suppressed.
        assert "A" not in result
        assert result["<other>"] == {"lower": 0, "upper": MIN_CELL_COUNT}
        assert result["B"] == {"lower": 20, "upper": 20}

    def test_rare_categories_are_merged_into_other(self):
        # 25 unique one-off values plus one common one: well past max_categories=20.
        df = pd.DataFrame({"code": [f"rare-{i}" for i in range(25)] + ["common"] * 30})
        statistics = {"code": _spec(["counts"])}
        local_result, errors = core.local_statistics(
            df, statistics, filters=None, min_cell_count=MIN_CELL_COUNT, max_categories=MAX_CATEGORIES
        )

        counts = local_result["columns"]["code"]["counts"]
        assert "common" in counts
        assert "<other>" in counts
        assert all(not label.startswith("rare-") for label in counts)
        assert len(counts) <= MAX_CATEGORIES

    def test_canary_unique_value_never_appears_in_output(self):
        sentinel = "patient-zxq-9f3e-unique-marker"
        df = pd.DataFrame({"code": ["common"] * 30 + [sentinel]})
        statistics = {"code": _spec(["counts"])}
        local_result, errors = core.local_statistics(
            df, statistics, filters=None, min_cell_count=MIN_CELL_COUNT, max_categories=MAX_CATEGORIES
        )
        columns, warnings = core.aggregate_statistics([local_result], statistics)

        rendered = repr(columns) + repr(warnings) + repr(errors)
        assert sentinel not in rendered

    def test_row_count_is_not_in_the_user_facing_result(self, healthy_df):
        statistics = {"age": _spec(["mean"])}
        local_result, _ = core.local_statistics(
            healthy_df, statistics, filters=None, min_cell_count=MIN_CELL_COUNT, max_categories=MAX_CATEGORIES
        )
        columns, _ = core.aggregate_statistics([local_result], statistics)

        assert "row_count" not in columns
        assert "row_count" not in columns.get("age", {})


class TestFaultIsolation:
    """AGENTS.md §1.3: one failing column or statistic must not fail the whole run."""

    def test_missing_column_only_knocks_out_that_column(self, healthy_df):
        statistics = {"age": _spec(["mean"]), "does_not_exist": _spec(["mean"])}
        result, errors = core.local_statistics(
            healthy_df, statistics, filters=None, min_cell_count=MIN_CELL_COUNT, max_categories=MAX_CATEGORIES
        )

        assert "age" in result["columns"]
        assert "does_not_exist" not in result["columns"]
        assert len(errors) == 1
        assert errors[0].code == "MISSING_COLUMN"
        assert errors[0].scope == "column:does_not_exist"

    def test_non_numeric_column_only_knocks_out_numeric_statistics(self, broken_df):
        # `age` has text values in `broken_df`; `counts` doesn't need numeric coercion.
        statistics = {"age": _spec(["mean", "counts"])}
        result, errors = core.local_statistics(
            broken_df, statistics, filters=None, min_cell_count=MIN_CELL_COUNT, max_categories=MAX_CATEGORIES
        )

        assert "counts" in result["columns"]["age"]
        assert "mean" not in result["columns"]["age"]
        assert any(e.code == "NON_NUMERIC" and e.scope == "statistic:age.mean" for e in errors)

    def test_empty_after_filter_raises_whole_node_error(self, healthy_df):
        statistics = {"age": _spec(["mean"])}
        with pytest.raises(AlgorithmError) as exc_info:
            core.local_statistics(
                healthy_df,
                statistics,
                filters={"age": {"gte": 10_000}},
                min_cell_count=MIN_CELL_COUNT,
                max_categories=MAX_CATEGORIES,
            )
        assert exc_info.value.code == "EMPTY_AFTER_FILTER"

    def test_aggregate_handles_a_node_missing_a_whole_column(self, healthy_df):
        statistics = {"age": _spec(["mean"])}
        shards = _shard(healthy_df, 3)
        local_results = [
            core.local_statistics(
                s, statistics, filters=None, min_cell_count=MIN_CELL_COUNT, max_categories=MAX_CATEGORIES
            )[0]
            for s in shards
        ]
        # Simulate one node where the column never made it into its result (e.g. it
        # was suppressed or missing there) -- aggregation must still produce a usable
        # (if partial) answer from the other nodes, with a warning, not a crash.
        del local_results[0]["columns"]["age"]

        columns, warnings = core.aggregate_statistics(local_results, statistics)

        assert columns["age"]["mean"] is not None
        assert any("missing or suppressed on 1 node" in w for w in warnings)
