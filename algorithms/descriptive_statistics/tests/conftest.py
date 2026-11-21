from pathlib import Path

import pandas as pd
import pytest

GENERATED_DIR = Path(__file__).parents[3] / "datavalgen" / "generated"


def _load(profile: str) -> pd.DataFrame:
    path = GENERATED_DIR / f"{profile}.csv"
    if not path.exists():
        pytest.skip(f"'{profile}' profile not generated yet; run `make data`")
    return pd.read_csv(path)


@pytest.fixture
def healthy_df() -> pd.DataFrame:
    return _load("healthy")


@pytest.fixture
def skewed_df() -> pd.DataFrame:
    return _load("skewed")


@pytest.fixture
def small_df() -> pd.DataFrame:
    return _load("small")


@pytest.fixture
def broken_df() -> pd.DataFrame:
    return _load("broken")


@pytest.fixture
def empty_df() -> pd.DataFrame:
    return _load("empty")


@pytest.fixture
def few_events_df() -> pd.DataFrame:
    return _load("few_events")
