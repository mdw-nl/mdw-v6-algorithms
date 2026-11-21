"""The study-file schema (AGENTS.md §9.5).

```yaml
profile: dev
collaboration: lung-study
initiating_org: alpha
algorithm: descriptive_statistics
version: 1.2.0
organizations: [alpha, beta]   # optional; default = all
params:
  statistics: {age: {stats: [mean]}}
output: results/descriptive
```
"""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Study(BaseModel):
    """A validated study file. Credentials never go in here (AGENTS.md §9.5)."""

    model_config = ConfigDict(extra="forbid")

    profile: str = Field(description="Server/collaboration profile; 'dev' is the local dev network.")
    collaboration: str = Field(description="Name of the collaboration to run against.")
    initiating_org: str = Field(description="Name of the organization creating the task.")
    algorithm: str = Field(
        description="Importable Python package name of the algorithm, e.g. 'descriptive_statistics'."
    )
    version: str = Field(description="Semver tag of the image to run. Never 'latest'.")
    organizations: list[str] | None = Field(
        default=None, description="Organization names to include; omit for every organization."
    )
    params: dict[str, Any] = Field(
        default_factory=dict, description="Parameters passed to the algorithm's central()."
    )
    output: str = Field(description="Directory results are written to.")
    image: str | None = Field(
        default=None,
        description=(
            "Explicit image reference override, e.g. 'descriptive_statistics:dev' for a locally pushed dev "
            "image. Before the registry/release pipeline exists, this is how a study targets an unreleased "
            "build; once images are published this should be left unset and 'algorithm'/'version' resolve "
            "the reference instead."
        ),
    )

    @field_validator("version")
    @classmethod
    def _no_latest(cls, value: str) -> str:
        if value.strip().lower() == "latest":
            raise ValueError("'version' must be a semver tag, never 'latest' (AGENTS.md §9.5)")
        return value

    def effective_params(self) -> dict[str, Any]:
        """`params` merged with the top-level `organizations` convenience field.

        AGENTS.md §9.5 documents `organizations` as a top-level study-file field (so the
        common case -- restrict the fan-out -- doesn't have to be duplicated inside the
        algorithm-specific `params` block). Setting it both places and disagreeing is
        almost certainly a mistake, not an override, so it's rejected rather than
        silently picking one.
        """
        if self.organizations is None:
            return dict(self.params)
        existing = self.params.get("organizations")
        if existing is not None and existing != self.organizations:
            raise ValueError(
                "study file sets 'organizations' both at the top level "
                f"({self.organizations!r}) and inside 'params' ({existing!r}) with "
                "different values -- remove one"
            )
        return {**self.params, "organizations": self.organizations}


def load_study(study_path: str | Path) -> Study:
    """Load and validate a study file. Raises `pydantic.ValidationError` on a bad shape."""
    path = Path(study_path)
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"Study file '{path}' must contain a YAML mapping at the top level")
    return Study.model_validate(raw)
