"""Regenerate the node-profile datasets used by every test suite (AGENTS.md §4, `make data`).

Deterministic: every profile is seeded explicitly. Output goes to `datavalgen/generated/`
(gitignored) as CSV, one file per profile, with the columns from `node_data_schema`.

`healthy` and `skewed` are realistic distributions generated through the registered
datavalgen factories. The other six profiles are pathological by construction (a
missing column, too few rows, ...) -- not meaningfully expressed as "a different random
distribution", so they're derived by perturbing a generated batch directly.
"""

from pathlib import Path

import numpy as np
import pandas as pd
from node_data_schema.factory import HealthyFactory, SkewedFactory

OUTPUT_DIR = Path(__file__).parent / "generated"


def _write(name: str, df: pd.DataFrame) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"{name}.csv"
    df.to_csv(path, index=False)
    print(f"wrote {len(df)} rows to {path}")


def healthy() -> pd.DataFrame:
    HealthyFactory.seed_random(20260101)
    return HealthyFactory.batch_dataframe(500)


def skewed() -> pd.DataFrame:
    SkewedFactory.seed_random(20260102)
    return SkewedFactory.batch_dataframe(500)


def small() -> pd.DataFrame:
    # Below the default min_rows (5, v6core.privacy.DEFAULTS.min_rows).
    HealthyFactory.seed_random(20260103)
    return HealthyFactory.batch_dataframe(3)


def broken() -> pd.DataFrame:
    HealthyFactory.seed_random(20260104)
    df = HealthyFactory.batch_dataframe(50)
    df = df.drop(columns=["site"])  # a missing column
    df["age"] = df["age"].astype(object)
    # Not "N/A"/"NA"/etc: those are in pandas' default CSV na_values and would just
    # read back as NaN, not survive as text that fails numeric coercion.
    df.loc[df.index[:5], "age"] = "unrecorded"  # text in a numeric column
    df["person_years"] = np.nan  # an all-NaN column
    return df


def empty() -> pd.DataFrame:
    HealthyFactory.seed_random(20260105)
    return HealthyFactory.batch_dataframe(1).iloc[0:0]  # headers only


def few_events() -> pd.DataFrame:
    # Below the default min_events (10, v6core.privacy.DEFAULTS.min_events).
    HealthyFactory.seed_random(20260106)
    df = HealthyFactory.batch_dataframe(200)
    df["event"] = 0
    df.loc[df.index[:2], "event"] = 1
    return df


def collinear() -> pd.DataFrame:
    HealthyFactory.seed_random(20260107)
    df = HealthyFactory.batch_dataframe(200)
    df["age_x2"] = df["age"] * 2 + 1  # perfectly collinear with `age`
    return df


def separation() -> pd.DataFrame:
    HealthyFactory.seed_random(20260108)
    df = HealthyFactory.batch_dataframe(200)
    df["separable_marker"] = df["event"].map({1: 100.0, 0: 0.0})  # perfectly predicts `event`
    return df


PROFILES = {
    "healthy": healthy,
    "skewed": skewed,
    "small": small,
    "broken": broken,
    "empty": empty,
    "few_events": few_events,
    "collinear": collinear,
    "separation": separation,
}


def main() -> None:
    for name, generate in PROFILES.items():
        _write(name, generate())


if __name__ == "__main__":
    main()
