# Handoff

Status snapshot and hard-won gotchas for whoever (human or agent) picks this repo up
next. **Read `AGENTS.md` in full first** — it's the actual spec (architecture, privacy
rules, testing, legacy porting notes per algorithm). This file is the supplement: what's
already proven to work, what's still open, and the traps that cost real debugging time
this round so you don't have to re-discover them.

## Where things stand

- **`descriptive_statistics` is the only ported algorithm**, and it's been validated
  end-to-end against a *live* 4-node vantage6 network (not just `MockAlgorithmClient`):
  `make smoke IMAGE=descriptive_statistics` passes against both the `healthy` and
  `faulty` dev-network scenarios (fault isolation confirmed: a node with bad data
  contributes a scoped error for the affected column/statistic only, not a crash).
- `packages/v6core/` (the shared library — envelope, provenance, privacy, participation,
  orchestration, params, serialization) is built and unit-tested (109 tests total,
  repo-wide).
- `dev-network/` (local 4-org vantage6 network + registry) and `runner/` (`v6run`, the
  researcher-facing CLI) are both built and working. `runner/` was also checked against
  `/home/dev/source/public/work/ideal4omop-poc/real-network` — a *real* (non-demo)
  vantage6 deployment — which surfaced and fixed real gaps (see **Runner / real-network
  gotchas** below).
- **The dev network is currently stopped** (`make net-down` was run at the end of this
  session for a clean handoff). Bring it up with `make net-up` (defaults to the
  `healthy` scenario; `SCENARIO=faulty make net-up` for the fault-injection one).
- `ruff format --check` / `ruff check` / `ty check` are all clean repo-wide. Keep them
  that way — `make lint` before every commit.

## Suggested next step: port the remaining 5 algorithms

AGENTS.md §3.4 and §14 already specify what goes where and what to carry over from the
legacy code — don't re-derive that, it's written out in detail there. The one thing
worth deciding explicitly is **order**, since `v6core.glm` and `v6core.survival` don't
exist yet and three of the five algorithms depend on the former:

1. **`v6core.glm` + `linear_regression`** first. Gaussian family converges in one round
   — it's the simplest way to stand up the shared GLM scaffold (IRLS loop, IRLS
   convergence/condition-number checks, IRLS checks from the legacy `linear_regression`/
   `poisson_regression` worth keeping per §14) without also fighting ADMM or convergence
   edge cases.
2. **`poisson_regression`** next — second GLM family, exercises the offset/exposure
   path, still no ADMM.
3. **`logistic_regression`** last of the three — absorbs `admm_logistic_regression` as
   the `l1_penalty > 0` path (§3.4). This is the hardest of the GLM family: the ADMM
   z-update, the "no classical SEs under an L1 penalty" warning, and `v6core.evaluation`
   replacing the legacy code's traceable per-patient prediction collection (§14's
   `admm_logistic_regression` notes).
4. **`v6core.survival` + `kaplan_meier`** — binned risk/event counts, shared time-binning
   and risk-set-guard code the Cox port also needs.
5. **`cox_regression`** last — ported from legacy `coxph` as-is per §8.1's exception
   (exact event times are kept, by deliberate decision), but needs a **regression test
   against the legacy `coxph` output on the same data** (§14 says so explicitly) — that's
   only possible once `cox_regression` actually exists to compare against, which is why
   it's last.

Use subagents for genuinely independent pieces of this (e.g. `v6core.glm` core math vs.
datavalgen schema work vs. dev-network scenario updates can usually run in parallel) —
that worked well this session. Don't delegate the *design* decisions (which checks move
from legacy central-only to per-node, what the params model looks like) — do those
yourself per AGENTS.md §13's checklist, then delegate implementation.

## Runner / real-network gotchas (from comparing against `ideal4omop-poc/real-network`)

A real vantage6 deployment has requirements the dev network doesn't, because the dev
network is deliberately unencrypted and has no 2FA. If you're about to point `v6run` at
anything other than the dev network, check these:

- **Encryption is implemented but never exercised against a real encrypted
  collaboration.** `v6run.runstudy._setup_encryption` reuses `profile.private_key_path`
  (the organization's *existing* node key) if configured, otherwise connects
  unencrypted. If a real collaboration enforces encryption and you see "uploading
  public key" or "does not match HQ's public key" in the logs on first connect, **stop
  immediately** — it means the configured key doesn't match what the server already has
  registered, and letting it proceed would overwrite the organization's registered key
  and break the node's own ability to decrypt tasks. Never point `private_key_path` at a
  freshly generated key for this reason.
- **MFA is implemented (`v6run run --mfa`) but likewise unverified against a real
  2FA-enabled account.**
- A non-`dev` profile has **no built-in defaults** — every `V6RUN_<NAME>_*` env var is
  required and the error message says exactly which one is missing. This is deliberate:
  don't add defaults for a profile that isn't `dev`, even for convenience.
- **Never put real credentials in any file inside this repo**, not even temporarily to
  test something — this isn't just the usual "secrets don't belong in git" rule. The
  `ideal4omop-poc` sibling project had a real incident: a file-watching feature
  surfaced a plaintext password to an agent the moment it was saved, completely
  independent of any `Read`/`Edit` permission rule on that path. Source real credentials
  from a file **outside** this checkout (`chmod 600`, `source`d before running `v6run`).
- The `Study.organizations` top-level field only reaches the algorithm via
  `Study.effective_params()` — if you add a new code path that reads `study.params`
  directly (instead of calling `effective_params()`), you will silently reintroduce the
  bug this session just fixed (a study meant to restrict the fan-out running against
  everyone instead). `validate()` and `run()` both already go through it; keep doing
  that.

## Other known traps (discovered the hard way this session)

- **Never call `client.result.get(id)`** (the single-result endpoint) — it 500s on
  vantage6 4.14.0-rc8's node-lite image (`proxy_results() got an unexpected keyword
  argument 'id'`, a real upstream bug, confirmed by reading the node's own logs). Always
  use the listing endpoint, `client.result.from_task(task_id)`, and match envelopes to
  organizations via each envelope's own `organization_id` field. `v6core.orchestration`
  already does this — don't bypass it with a direct client call in a new algorithm.
- **Never call `client.wait_for_results()`** (node side) or rely on an unbounded wait
  (runner side) — both hang forever if an organization in the collaboration has no node
  running. `fan_out()` and `v6run.runstudy._wait_for_task` both poll against an explicit
  deadline instead; reuse them, don't reinvent.
- **`MockAlgorithmClient.Task.create`'s return-type annotation is wrong** in
  `vantage6-algorithm-tools==4.14.0` (`-> int` when it's really a dict), which breaks
  structural (`Protocol`) typing against the mock client specifically. `v6core._typing`
  has an `AnyAlgorithmClient = AlgorithmClientLike | MockAlgorithmClient` union to work
  around it — use that union in new code that needs to accept either client, don't
  re-derive a narrower Protocol that the mock client fails to satisfy.
- **`dev-network/scripts/devnet.py`'s `reset` must wipe local vantage6 state**, not just
  stop containers — `v6 server start` bind-mounts the server's SQLite DB from
  `~/.local/share/vantage6/server/<name>` on the *host*, which survives `docker down`.
  Switching scenarios without wiping it hits `UNIQUE constraint failed: organization.name`
  on reimport. `_remove_local_vantage6_state()` already handles this; call `cmd_reset`,
  don't hand-roll a `down` + `up`.
- **`push_image.sh` takes `IMAGE_NAME` and `TAG` as two separate positional args**, not
  a single `name:tag` string — `push_image.sh descriptive_statistics dev`, not
  `push_image.sh descriptive_statistics:dev`.
- **Privacy: merge both below-threshold *and* overflow-past-`max_categories` categories
  into `"<other>"`.** An earlier version of `_compute_counts` only merged overflow, which
  meant a category below `min_cell_count` was still shown under its own label with a
  suppressed range — itself a label-disclosure bug. The canary test in
  `descriptive_statistics/tests/test_core.py` (`TestPrivacy`) is what catches this class
  of bug; make sure any new per-category statistic has an equivalent canary.
- **`to_jsonsafe()` must check `value is pd.NA or value is pd.NaT` before
  `np.isscalar`/`pd.isna`** — the wrong order lets `pd.NA` slip through unconverted.
- The algorithm store isn't running in the dev network — MDW's `ghcr.io` mirror has no
  `algorithm-store` image, and `harbor2.vantage6.ai` is unreachable from this sandbox
  (DNS failure). This is an environmental gap, not a code bug; `dev-network/README.md`
  documents it. `make smoke` and everything else work fine without it.

## Still unimplemented / open

- `make store-json` (auto-generating `algorithm.json` from a params model) is a stub —
  `descriptive_statistics/algorithm.json` is hand-written. Worth automating once a
  second algorithm exists to generalize the pattern from.
- Docker-in-CI for `make smoke` (standing up the full multi-container dev network
  inside a GitHub Actions job) is tracked but not investigated — see AGENTS.md §15.
  `make smoke` has only ever been run manually against the live dev network so far.
- Secondary/deterministic-noise suppression in `descriptive_statistics` has primitives
  in `v6core.privacy` (`deterministic_pick`, `safe_log`) but isn't wired in — intentional
  for the first version, documented in the algorithm's own README.

## Useful reference material (not part of this repo)

- `/home/dev/source/public/work/v6-infrastructure-sh/algorithms` — the legacy algorithms
  being ported (§14's subject).
- `/home/dev/source/public/work/v6-glm`, `v6-cox-ph`, `v6-kaplan-meier`,
  `v6-descriptive-statistics` — other MDW repos with relevant prior art for the
  corresponding analysis.
- `/home/dev/source/public/work/datavalgen` and `datavalgen-model-example` — the
  synthetic-data generation library this repo's `datavalgen/schemas/` plugs into.
- `/home/dev/source/public/work/ideal4omop-poc/real-network` — real (non-demo) vantage6
  deployment scripts; read its README before assuming `v6run` works unmodified against
  any real collaboration — it's where this session's encryption/MFA/credentials
  findings came from, and it also has porting-relevant notes for `kaplan_meier`/
  `cox_regression` (a real schema with no numeric time-to-event column, and a
  `{"mode": "presence"}` trick for deriving a binary outcome from a date column).
