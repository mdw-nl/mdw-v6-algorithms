# v6run

The researcher-facing CLI and Python API for running studies against this repo's
algorithms (AGENTS.md §9.4). Replaces the per-algorithm `run_study.py` scripts: write a
study file once, then `v6run validate` it before anything touches a server, or
`v6run run` it for real.

## Installation

Not published yet. Once the runner has a release tag, researchers install it straight
from this public repo, pinned to that tag, with no SSH key or package index needed:

```bash
pip install "git+https://github.com/<org>/<repo>.git@runner/v<semver>#subdirectory=runner"
```

Inside this repo's own workspace, it's already installed editable via `uv sync` (or
`make setup`).

## CLI

```bash
v6run validate study.yaml          # local only -- no server connection
v6run run study.yaml --out results/
v6run list                         # not implemented yet
```

`validate` checks the study file's shape and validates `params` against the
algorithm's params model (found by importing `<algorithm>.params`) -- entirely
offline. `run` does the same validation first, then creates the task, waits for it
(bounded by `--wait-timeout`, default 600s -- it never waits forever, independent of
any `timeout_s` the request itself carries for the algorithm's own node fan-out), and
writes `result.json` (the full envelope), `params.json` (what was actually sent) and a
readable `summary.md` to the output directory. Participation and warnings are also
printed directly to stdout, so a `partial` result is never mistaken for a clean one.

## Python API

```python
from v6run import run, validate

result = validate("study.yaml")
if result.ok:
    run_result = run("study.yaml", out_dir="results/")
    print(run_result.envelope["status"])
```

## Study file

See AGENTS.md §9.5 for the full shape. One field worth calling out: `image` is an
optional override (e.g. `descriptive_statistics:dev`) for running a locally built/
pushed image before the registry and release pipeline exist. Once images are
published, leave it unset -- `algorithm` + `version` resolve the image reference.

## Server profiles

`profile: dev` in a study file resolves to the local dev network
(`dev-network/`) by default: `http://localhost:5070`, api path `/api`.

Credentials are never in the study file or in code (AGENTS.md §9.5) -- set them via
environment variables:

| Variable | Default | Notes |
|---|---|---|
| `V6RUN_USERNAME` | `dev_admin` | Dev network's well-known account; fine to default since it's fake. |
| `V6RUN_PASSWORD` | `password` | Same. |
| `V6RUN_SERVER_URL` | `http://localhost` | |
| `V6RUN_PORT` | `5070` | |
| `V6RUN_API_PATH` | `/api` | |

Only the `dev` profile is defined so far (`v6run.profiles.resolve_profile`). Add a
new entry there when a real server/collaboration profile is needed -- don't invent a
parallel mechanism.

## Known gaps (first version)

- **No plotting.** `summary.md` is text only: status, participation table, errors,
  warnings, a pointer to `result.json`. No coefficient tables, forest plots, KM
  curves, or ROC/calibration charts yet. AGENTS.md expects these eventually to live
  in the runner, never in an algorithm image -- this is a deliberate gap in this
  first version, not a design decision to skip them permanently.
- **`v6run list`** is a stub.
- Only the `dev` profile is defined.
