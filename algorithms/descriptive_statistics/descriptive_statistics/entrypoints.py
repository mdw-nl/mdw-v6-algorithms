"""vantage6 shell for `descriptive_statistics` (AGENTS.md §3.1): thin, no statistics here.

`central()` validates params, fans the request out to every node, applies the
`min_rows`/quorum floors, and aggregates. `compute_local_stats()` is the per-node
function; it's never called directly (the provenance guard refuses that, AGENTS.md
§8.4) -- only as a subtask `central()` creates through `v6core.orchestration.fan_out`.
"""

import importlib.metadata

import pandas as pd
from vantage6.algorithm.client import AlgorithmClient
from vantage6.algorithm.tools.decorators import algorithm_client, data

from descriptive_statistics import core
from descriptive_statistics.params import DescriptiveStatisticsParams
from v6core import participation, privacy
from v6core.envelope import CentralError, CentralResult, NodeError, safe_federated
from v6core.orchestration import fan_out
from v6core.params import ParamsError, parse_params
from v6core.privacy import PrivacyParamError

ALGORITHM_NAME = "descriptive_statistics"
ALGORITHM_VERSION = "0.1.0"


def _v6core_version() -> str:
    try:
        return importlib.metadata.version("v6core")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0+unknown"


def _count_suppressed_cells(columns: dict) -> int:
    # The shapes here are the *aggregated* (central-facing) ones from
    # `core.aggregate_statistics`, not the per-node sufficient-statistics dicts --
    # `mean`/`std` aggregate to a bare `float | None`, `minmax` to a `{min, max}` dict,
    # `counts`/`binned_counts` to a `{label: {lower, upper}}` dict, and
    # `nrows`/`nans`/`outliers` to the standard `{value, suppressed}` shape.
    count = 0
    for column_result in columns.values():
        for statistic, value in column_result.items():
            if statistic in ("counts", "binned_counts"):
                count += sum(1 for bounds in (value or {}).values() if bounds["lower"] != bounds["upper"])
            elif statistic in ("mean", "std"):
                count += value is None
            elif statistic == "minmax":
                count += value is not None and value.get("min") is None
            elif isinstance(value, dict) and value.get("suppressed"):
                count += 1
    return count


@algorithm_client
def central(client: AlgorithmClient, **raw_params) -> dict:
    result = CentralResult(
        algorithm_name=ALGORITHM_NAME,
        algorithm_version=ALGORITHM_VERSION,
        v6core_version=_v6core_version(),
        params=raw_params,
    )

    try:
        params = parse_params(DescriptiveStatisticsParams, raw_params)
    except ParamsError as exc:
        result.status = "error"
        result.errors = [CentralError("INVALID_PARAM", "node", m) for m in exc.messages]
        return result.to_dict()

    try:
        min_cell_count, cell_below_default = privacy.resolve_threshold(
            "min_cell_count", params.min_cell_count
        )
        min_rows, rows_below_default = privacy.resolve_threshold("min_rows", params.min_rows)
        max_categories, categories_below_default = privacy.resolve_threshold(
            "max_categories", params.max_categories
        )
    except PrivacyParamError as exc:
        result.status = "error"
        result.errors = [CentralError("INVALID_PARAM", "node", str(exc))]
        return result.to_dict()

    result.privacy = {
        "thresholds": {
            "min_cell_count": min_cell_count,
            "min_rows": min_rows,
            "max_categories": max_categories,
        },
        "below_default": [
            name
            for name, below in (
                ("min_cell_count", cell_below_default),
                ("min_rows", rows_below_default),
                ("max_categories", categories_below_default),
            )
            if below
        ],
    }

    try:
        orgs = participation.select_organizations(client.organization.list(), params.organizations)
    except participation.ParticipationError as exc:
        result.status = "error"
        result.errors = [exc.to_central_error()]
        return result.to_dict()

    org_name_by_id = {org["id"]: org["name"] for org in orgs}
    statistics_spec = {name: spec.model_dump() for name, spec in params.statistics.items()}

    outcomes = fan_out(
        client,
        method="compute_local_stats",
        organizations=list(org_name_by_id),
        kwargs={
            "statistics": statistics_spec,
            "filters": params.filters,
            "min_cell_count": min_cell_count,
            "max_categories": max_categories,
        },
        timeout_s=params.timeout_s,
        name="descriptive_statistics_local",
        description="Compute local descriptive statistics",
    )

    usable_results: dict[int, dict] = {}
    failed: dict[int, str] = {}
    for org_id, outcome in outcomes.items():
        if outcome.status == "timeout":
            failed[org_id] = "TIMEOUT"
        elif outcome.status == "error":
            failed[org_id] = "NODE_FAILED"
        else:
            envelope = outcome.envelope or {}
            if envelope.get("status") == "error":
                node_errors = envelope.get("errors") or [{}]
                failed[org_id] = node_errors[0].get("code", "NODE_FAILED")
            else:
                usable_results[org_id] = envelope.get("result", {})
                for node_error in envelope.get("errors") or []:
                    org_name = org_name_by_id[org_id]
                    result.warnings.append(
                        f"{org_name}: {node_error.get('scope')}: {node_error.get('message')}"
                    )

    row_counts = {org_id: r.get("row_count") for org_id, r in usable_results.items()}
    qualifying_ids, below_rows = participation.apply_min_floor(row_counts, min_rows, reason="BELOW_MIN_ROWS")
    failed.update({org_id: reason for org_id, reason in below_rows.items() if org_id not in failed})

    result.participation = [
        participation.Participant(
            organization=org_name_by_id[org_id],
            status="included" if org_id in qualifying_ids else "failed",
            reason=failed.get(org_id),
        ).to_dict()
        for org_id in org_name_by_id
    ]

    try:
        participation.check_quorum(len(qualifying_ids), params.min_organizations)
    except participation.ParticipationError as exc:
        result.status = "error"
        result.errors = [exc.to_central_error()]
        return result.to_dict()

    columns, agg_warnings = core.aggregate_statistics(
        [usable_results[org_id] for org_id in qualifying_ids], statistics_spec
    )
    result.warnings.extend(agg_warnings)
    result.result = {"columns": columns}
    result.privacy["suppressed_cells"] = _count_suppressed_cells(columns)
    result.status = "partial" if result.warnings or len(qualifying_ids) < len(org_name_by_id) else "ok"
    return result.to_dict()


@data(1)
@algorithm_client
@safe_federated()
def compute_local_stats(
    client: AlgorithmClient,
    df: pd.DataFrame,
    statistics: dict,
    filters: dict | None,
    min_cell_count: int,
    max_categories: int,
) -> tuple[dict, list[NodeError]]:
    return core.local_statistics(df, statistics, filters, min_cell_count, max_categories)
