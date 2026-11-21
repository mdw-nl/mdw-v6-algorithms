"""Factories for the `node_data` datavalgen model (AGENTS.md §4).

`__random_seed__` makes every profile deterministic (AGENTS.md §4: "Generation must be
deterministic"). `datavalgen/generate_profiles.py` drives these directly for the
pathological profiles (small/broken/empty/few_events/collinear/separation) that aren't
meaningfully expressed as "a different random distribution" the way healthy/skewed are.
"""

from typing import Literal

from datavalgen.factory import BaseDataModelFactory
from polyfactory.decorators import post_generated

from .model import NodeDataModel

_SITES: tuple[Literal["alpha", "beta", "gamma"], ...] = ("alpha", "beta", "gamma")


class HealthyFactory(BaseDataModelFactory[NodeDataModel]):
    """A normal, mid-sized dataset: plenty of rows, plenty of events, no pathology."""

    __model__ = NodeDataModel
    __random_seed__ = 20260101

    @classmethod
    def age(cls) -> int:
        return int(min(max(round(cls.__random__.gauss(50, 15)), 0), 100))

    @classmethod
    def sex(cls) -> Literal["F", "M"]:
        return "F" if cls.__random__.random() < 0.5 else "M"

    @classmethod
    def site(cls) -> Literal["alpha", "beta", "gamma"]:
        return cls.__random__.choices(_SITES, weights=[1, 1, 1])[0]

    @classmethod
    def smoker(cls) -> Literal["Yes", "No"]:
        return "Yes" if cls.__random__.random() < 0.2 else "No"

    @classmethod
    def num_visits(cls) -> int:
        return min(max(int(round(cls.__random__.gauss(5, 3))), 0), 50)

    @post_generated
    @classmethod
    def person_years(cls, num_visits: int) -> float:
        base = cls.__random__.uniform(0.5, 5.0)
        return round(min(max(base, 0.1), 10.0), 2)

    @classmethod
    def time_to_event(cls) -> float:
        value = cls.__random__.expovariate(1.0 / 400.0)
        return round(min(max(value, 1.0), 3650.0), 1)

    @classmethod
    def event(cls) -> Literal[0, 1]:
        return 1 if cls.__random__.random() < 0.4 else 0


class SkewedFactory(HealthyFactory):
    """A very different distribution: skewed young, rarely smokes, one dominant site."""

    __model__ = NodeDataModel
    __random_seed__ = 20260102

    @classmethod
    def age(cls) -> int:
        # Heavily right-skewed: mostly young, with a long tail toward older ages.
        value = cls.__random__.gammavariate(2.0, 8.0)
        return int(min(max(round(value), 0), 100))

    @classmethod
    def site(cls) -> Literal["alpha", "beta", "gamma"]:
        return cls.__random__.choices(_SITES, weights=[8, 1, 1])[0]

    @classmethod
    def smoker(cls) -> Literal["Yes", "No"]:
        return "Yes" if cls.__random__.random() < 0.02 else "No"
