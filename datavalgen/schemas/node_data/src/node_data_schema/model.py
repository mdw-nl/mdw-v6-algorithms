"""Shared node-data model for this repo's datavalgen profiles (AGENTS.md §4).

One schema serves every algorithm family so profiles don't have to be duplicated per
image: a continuous covariate (`age`), categorical covariates (`sex`, `site`), a count
outcome with exposure (`num_visits`, `person_years`), and a time-to-event outcome
(`time_to_event`, `event`).
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class NodeDataModel(BaseModel):
    age: Annotated[int, Field(ge=0, le=100, description="Age in completed years.")]
    sex: Annotated[Literal["F", "M"], Field(description="Administrative sex marker.")]
    site: Annotated[Literal["alpha", "beta", "gamma"], Field(description="Fictional recruiting site.")]
    smoker: Annotated[Literal["Yes", "No"], Field(description="Whether the subject is a smoker.")]
    num_visits: Annotated[
        int, Field(ge=0, le=50, description="Count of care visits in the observation window.")
    ]
    person_years: Annotated[
        float, Field(gt=0, le=10.0, description="Exposure time in years, for a rate per unit of exposure.")
    ]
    time_to_event: Annotated[
        float, Field(gt=0, le=3650.0, description="Time to event or censoring, in days.")
    ]
    event: Annotated[Literal[0, 1], Field(description="1 if the event was observed, 0 if censored.")]
