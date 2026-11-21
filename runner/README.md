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

`profile: dev` in a study file resolves to the local dev network (`dev-network/`) by
default: `http://localhost:7601`, api path `/api`, the dev network's well-known fake
`dev_admin` account. All of it is overridable, and any *other* profile name works the
same way with no built-in defaults -- every setting for a profile named `<name>` comes
from an environment variable `V6RUN_<NAME>_*` (uppercased), and a real profile fails
loudly if a required one is missing rather than falling back to anything:

| Variable | Required | `dev` default | Notes |
|---|---|---|---|
| `V6RUN_<NAME>_SERVER_URL` | yes | `http://localhost` | |
| `V6RUN_<NAME>_PORT` | yes | `7601` | |
| `V6RUN_<NAME>_API_PATH` | no | `/api` | |
| `V6RUN_<NAME>_USERNAME` | yes | `dev_admin` | |
| `V6RUN_<NAME>_PASSWORD` | yes | (dev network's fake password) | |
| `V6RUN_<NAME>_DATABASE_LABEL` | no | `default` | Must match what every node in the collaboration registered its dataset under. |
| `V6RUN_<NAME>_PRIVATE_KEY_PATH` | no | unset (unencrypted) | See **Encryption** below. |

Credentials never go in a study file or in code (AGENTS.md §9.5), following grimoire's
secrets policy (`company/security.md`): set them from a file **outside this repo**
(e.g. `~/.v6run-prod.env`, `chmod 600`, `source`d before running `v6run`) -- never
inside the project directory, where an editor or file-watching tool could surface a
secret in plaintext the moment it's saved.

### Encryption

A collaboration that enforces end-to-end encryption rejects an unencrypted client
outright ("Your collaboration requires encryption, but input is not encrypted!"). Set
`V6RUN_<NAME>_PRIVATE_KEY_PATH` to your organization's **existing** node encryption
private key -- the same file your node's own `config.yaml` already points at under
`encryption.private_key`. vantage6 encryption keys are per-organization and shared with
the node, so pointing at the existing key means the client's `setup_encryption()` call
finds a match already registered on the server and uploads nothing. **Never point this
at a freshly generated key** -- that would overwrite the organization's registered
public key and break the node's own ability to decrypt tasks until its config is
updated to match. If a run ever logs "uploading public key" or "does not match HQ's
public key," stop and recheck `PRIVATE_KEY_PATH` before running anything else.

This is implemented (`v6run.runstudy._setup_encryption`) but not yet exercised against
a real encryption-enforcing collaboration -- the dev network is unencrypted, so only
the "no key configured" path has been tested live.

### Two-factor authentication

Pass `--mfa` to `v6run run` on a server with 2FA enabled; it prompts for a fresh
six-digit code right before authenticating (a TOTP code is single-use and expires in
seconds, so there's nothing to usefully store ahead of time). Omit it if the account
has no 2FA.

## Known gaps (first version)

- **No plotting.** `summary.md` is text only: status, participation table, errors,
  warnings, a pointer to `result.json`. No coefficient tables, forest plots, KM
  curves, or ROC/calibration charts yet. AGENTS.md expects these eventually to live
  in the runner, never in an algorithm image -- this is a deliberate gap in this
  first version, not a design decision to skip them permanently.
- **`v6run list`** is a stub.
- Only the `dev` profile is defined.
