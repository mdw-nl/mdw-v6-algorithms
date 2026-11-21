# AGENTS.md: Standard vantage6 algorithm library

This repo holds our **standard, reusable vantage6 algorithms**, the **shared library**
they are built on, a **local test vantage6 network**, and the **tooling researchers use to
run them**. One image version must work for every project without being rebuilt or edited.
Project-specific details (column names, outcome coding, strata, thresholds) are passed in
as **request parameters**. They never go into the code and never into node configuration.

## 0. Conventions come from grimoire first

This repo follows the policies and conventions of our **grimoire** repo
(`mdw-nl/grimoire`): code style, git workflow, branching, commit messages, reviews,
secrets handling, CI and documentation. Read grimoire before working here.
- grimoire covers the **general** rules. This file covers **only** what is specific to
  this repo.
- If the two conflict, **grimoire wins**. Flag the conflict so this file can be fixed.
- Don't duplicate grimoire rules in here. Link to them instead.

Read this file in full before changing anything. If a rule here conflicts with a request,
stop and say so. Do not quietly break the rule.

---

## 1. Non-negotiables

1. **Zero node-side setup.** An algorithm must run on a stock vantage6 node that has the
   project data attached as a database. No `algorithm_env`, no `.env` files, no extra
   mounts, no node policies beyond allowing our images. Anything an algorithm needs comes
   from request parameters or is baked into the image.
2. **No project-specific values in code.** Column parameters are **required and have no
   default**. No hard-coded column names (the legacy `"age"`, `"Survival.time"`,
   `"deadstatus.event"` defaults must go), category values, outcome codings, paths,
   organization names or credentials. Generic defaults are fine, for example
   `max_iterations=25`.
3. **One failing node, column or statistic must not fail the whole run.** Failures
   degrade the result, are reported in the output, and the run continues while the quorum
   (`min_organizations`) is still met. Nothing may hang forever.
4. **Shared logic lives in `v6core`, never copied.** If two algorithms need the same
   helper, it goes in `packages/v6core`. §3.2 lists what already has to move there.
5. **One vocabulary.** Parameter names, error handling and output shapes are identical
   across algorithms (§9). No per-algorithm synonyms.
6. **Nothing that leaves a node can be traced back to an individual patient.** Aggregates
   are fine to share. Row-level or single-patient information is not. See §8.
7. **Every algorithm passes the standard test suites (§10) and the dev-network smoke test
   (§5)** before it is released.
8. **Only synthetic data goes in this repo**, generated with datavalgen (§4). No real
   patient data, ever, not even "anonymised" extracts.

---

## 2. Repository layout

```
.
├── AGENTS.md
├── README.md                     # For researchers: what's available, how to run it
├── Makefile                      # Single entry point for every dev task (§6)
├── versions.toml                 # Single source of truth: vantage6, Python, base image versions
├── packages/
│   └── v6core/                   # Shared library, installed into every algorithm image
│       ├── v6core/
│       │   ├── spec.py           # Data-spec vocabulary: columns, filters, derive, inliers, encoding
│       │   ├── coerce.py         # Type coercion + column validation, value-free errors
│       │   ├── envelope.py       # Node + central result envelopes, error codes, safe_federated
│       │   ├── orchestration.py  # fan_out(), timeouts, per-org kwargs
│       │   ├── participation.py  # Organization selection, min_rows / min_events, quorum
│       │   ├── iteration.py      # Shared driver for iterative fits (IRLS/Newton/ADMM)
│       │   ├── glm.py            # IRLS for GLM families (gaussian, binomial, poisson + offset)
│       │   ├── survival.py       # Time binning, risk-set guard, event derivation (KM + Cox)
│       │   ├── inference.py      # Coefficient tables, Wald/LR/F tests, CIs, rank/condition checks
│       │   ├── standardize.py    # Federated centre/scale + back-transform of coefficients
│       │   ├── split.py          # Deterministic train/validation split
│       │   ├── evaluation.py     # Federated ROC/AUC/calibration from binned counts
│       │   ├── provenance.py     # "Was this federated call spawned by our central?" guard
│       │   ├── params.py         # Parameter models -> validation, docs, store metadata
│       │   ├── privacy.py        # Threshold defaults + absolute minimums, small-cell checks, safe logging
│       │   └── serialization.py  # numpy/NaN -> JSON-safe
│       └── tests/
├── algorithms/
│   └── <name>/                   # One image per analysis (§3.4)
│       ├── <name>/               # Python package: core.py (pure), entrypoints.py (vantage6 shell)
│       ├── tests/
│       ├── Dockerfile
│       ├── algorithm.json        # Algorithm-store metadata (generated, committed)
│       ├── README.md             # Params, outputs, method, privacy behaviour
│       └── CHANGELOG.md
├── runner/                       # `v6run` CLI + Python API for researchers (§9)
├── dev-network/                  # Local test vantage6 network (§5)
│   ├── README.md
│   ├── config/                   # Hub/server, store, UI and node configs (dev only, fake creds)
│   ├── scenarios/                # Named network setups: healthy, faulty, ...
│   └── scripts/                  # up / down / reset / status / seed / push-image
├── datavalgen/                   # datavalgen schemas for our synthetic test data (§4)
│   ├── schemas/                  # One schema per node profile
│   └── generated/                # Output (gitignored); regenerate with `make data`
├── examples/studies/             # Example study YAML files; all run against the dev network
├── docker/base.Dockerfile        # Pinned base image shared by all algorithms
└── .github/workflows/            # (or CI as prescribed by grimoire)
```

Build every image with the **repo root as the build context** so `packages/v6core` can be
installed into it.

---

## 3. Architecture

### 3.1 Pure core, thin vantage6 shell
Each image is split into two layers:

- **`core.py`**: pure functions on `pandas.DataFrame`s, numpy arrays and plain dicts. It
  has **no vantage6 imports**. It contains the local computation (`local_*`) and the
  aggregation (`aggregate_*` / `update_*`). All the statistics live here and all the unit
  tests target it.
- **`entrypoints.py`**: the vantage6 functions (central and federated). They only:
  validate params → prepare the data through `v6core.spec` → call `core` → wrap the result
  in an envelope. Keep them short. If an entrypoint grows logic, move that logic into
  `core` or `v6core`.

Why this matters:
- The statistics can be tested against pooled reference implementations without docker or
  a network.
- **We target vantage6 4.x.** `vantage6-algorithm-tools` 4.x, the `@data(1)` /
  `@algorithm_client` decorators, and `wrap_algorithm` as the image entrypoint. The exact
  version is pinned in `versions.toml`, and the dev network and the runner's client use
  the same version. Don't use 5.x-only features (`@dataframe`, sessions, step-type
  decorators).
- Keeping vantage6-specific code in `entrypoints.py`, `v6core.orchestration` and
  `v6core.provenance` means a later move to 5.x only touches those files.
- Only use methods that give the **same result as a pooled analysis** (closed form,
  IRLS/Newton, ADMM run to convergence). Approximate methods such as FedAvg are not used.

### 3.2 Shared building blocks (must be used, never re-implemented)
These are patterns the legacy algorithms each implemented separately, often slightly
differently. They live in `v6core`, and algorithms call them.

| Building block | Module | Replaces legacy |
|---|---|---|
| Column presence/numeric checks, duplicate-column and outcome-in-predictors checks | `coerce` | `_require_columns`, `_clean_and_validate`, the duplicate checks in linear/Poisson |
| Binary derivation (`presence`/`equals`/`isin`/`invert`) | `spec` | `_derive_binary` (copied into 5 files) |
| Organization selection by name | `participation` | `_filter_organizations` (copied into 8 files) |
| `min_rows` / `min_events` exclusion + `min_organizations` quorum | `participation` | The same ~25-line block in every `central()` |
| Rows/events-per-parameter guard | `participation` | `max_pct_vars_vs_obs` in each regression |
| Iteration loop: max iterations, tolerance, NaN/Inf stop, convergence report | `iteration` | Separate loops in Cox, Poisson, ADMM, FedAvg |
| IRLS for gaussian / binomial / poisson (+ offset), null deviance, dispersion | `glm` | Poisson IRLS (generalised), linear normal equations (= one IRLS step) |
| Covariate standardisation + back-transform of β, SE and covariance | `standardize` | Cox's centre/scale. Poisson only clips `eta` |
| Rank check, condition-number warning, safe inverse, coefficient table, Wald/LR/F tests | `inference` | `_safe_inverse`, `_build_results_table` variants |
| Deterministic train/validation split | `split` | `_split_train_val`, `df.sample(random_state=seed)` |
| ROC/AUC/calibration from binned counts | `evaluation` | ADMM's `collect_predictions` + sklearn on pooled predictions |
| Provenance guard | `provenance` | Cox's `ensure_spawned_by_central` |

### 3.3 Data-agnostic contract (`v6core.spec`)
All algorithms describe their input data with the same vocabulary, so one image serves any
schema:
- **columns**: every column an algorithm reads is a required parameter.
- **filters**: equality, `isin` and range (`gte`/`gt`/`lte`/`lt`).
- **representation**: binary from `presence` / `equals` / `isin`, with `invert`.
- **inliers**: a numeric range or allowed values. Values outside it are counted as
  outliers.
- **categorical encoding**: levels agreed across nodes, plus a reference level. This is
  needed because the regressions currently require already-numeric covariates.
- **missing data**: complete-case by default. The **same row set** is used in every phase
  of a run, and the excluded rows are always counted.

### 3.4 Images: one per analysis
- **Each analysis is its own image.** Node admins approve algorithms per image (the
  node's `allowed_algorithms` matches image names), so a node must be able to allow
  linear regression but not logistic regression, or descriptive statistics but not Cox.
  Never bundle several analyses into one image behind a "which analysis" parameter.
- Maintenance is shared through `v6core`, not through bundling. An image is mostly a
  thin wrapper: its own params model, entrypoints and README, calling shared
  machinery. If an image grows a lot of code another image could use, move that code
  to `v6core`.
- Each image exposes **one** user-facing central function. Its federated functions are
  internal.
- **Planned images:**

  | Image | Method | Replaces legacy |
  |---|---|---|
  | `descriptive_statistics` | Per-node sufficient statistics, combined centrally | `fed_statistics`, `average` (the mean is one of its statistics) |
  | `linear_regression` | `v6core.glm`, gaussian family (converges in one step) | `linear_regression` |
  | `logistic_regression` | `v6core.glm`, binomial family. When `l1_penalty > 0` it uses ADMM | `admm_logistic_regression`. FedAvg `logistic_regression` is **retired** |
  | `poisson_regression` | `v6core.glm`, poisson family, optional `exposure_col` offset | `poisson_regression` |
  | `kaplan_meier` | Binned risk/event counts | `kaplan_meier` |
  | `cox_regression` | The legacy `coxph` method, ported as-is: pooled Newton–Raphson on the partial likelihood with exact event times (§8.1 exception) | `coxph` |

- `logistic_regression`: the user never chooses between IRLS and ADMM. The method used is
  reported in `fit.method`. With an L1 penalty, `std_error`, `p_value` and the CIs are
  `null` with a warning, because classical SEs aren't valid for penalised fits.
- Survival-specific shared code (time binning, the risk-set guard, event derivation) used
  by both `kaplan_meier` and `cox_regression` goes in `v6core` (e.g.
  `v6core/survival.py`).

---

## 4. Test data: datavalgen

We generate synthetic data with **datavalgen**, our tool for defining data schemas and
generating matching datasets. See the datavalgen repo for how to use it.
- Schemas live in `datavalgen/schemas/`. Generated files go to `datavalgen/generated/`
  (gitignored). Regenerate them with `make data`. Generation must be deterministic (fixed
  seeds).
- Keep **one schema per node profile**, not one per test. Profiles should cover at
  least:
  - `healthy`: a normal, mid-sized dataset
  - `small`: below the default `min_rows`
  - `skewed`: a very different distribution
  - `broken`: a missing column, text in a numeric column, an all-NaN column
  - `empty`: headers only
  - `few_events`: below `min_events`, for survival and binary outcomes
  - `collinear`: two perfectly collinear covariates, for the rank checks
  - `separation`: a covariate that perfectly predicts a binary outcome
- Schemas need columns for every model family: continuous, binary, count + exposure,
  time-to-event + event indicator, and categorical.
- Unit tests, the federated-equals-pooled tests and the dev network all use these same
  generated datasets.

---

## 5. Dev network (`dev-network/`)

A local vantage6 network for testing images end to end, the same way a project network
would run them.

- **Version:** the vantage6 version is pinned in `versions.toml` and matches the targeted
  major (4.x). The scripts wrap the vantage6 4.x CLI (`v6 dev ...`, `v6 server ...`,
  `v6 node ...`). Don't call the CLI directly from other places.
- **Components:** server, UI, our own algorithm store (§9.4), and at least 3 organizations with
  running nodes, plus **1 organization registered in the collaboration with no node
  running** (to test timeouts and hangs).
- **Data:** each node mounts a datavalgen profile (§4) as its `default` database. Which
  node gets which profile is set per scenario in `dev-network/scenarios/`.
- **Scenarios** (`make net-up SCENARIO=<name>`):
  - `healthy`: every node uses `healthy` or `skewed`
  - `faulty`: one `broken` node, one `small` or `few_events` node, one offline
    organization
  - add more as needed
- **Images:** nodes pull from a local registry. `make push-local IMAGE=<name>` builds,
  tags and pushes there. Node configs allow only that registry. That is also the **only**
  node setting we rely on, which mirrors the zero-setup rule for real nodes.
- **Credentials:** dev-only, fake, committed in `dev-network/config/`, and clearly
  labelled as such. They must never be reused anywhere else.
- **Idempotent scripts:** `net-up` on a running network is a no-op. `net-reset` wipes all
  state and recreates it from config.
- **Version-sensitive code is tested here.** Anything that depends on vantage6 internals
  (`v6core.provenance`, task/run status polling in `orchestration`) has a dev-network
  test. The mock client can't exercise it.
- The runner has a `dev` profile, so every file in `examples/studies/` runs against the
  dev network with no edits.

---

## 6. Developer workflow (Makefile)

Everything goes through `make`, both for humans and for agents. Don't invent ad-hoc
commands in docs or CI. Add a target instead.

| Target | Does |
|---|---|
| `make setup` | Create the venv and install `v6core`, `runner` and dev dependencies (editable) |
| `make lint` | Run the linters and type checkers prescribed by grimoire |
| `make test [IMAGE=<name>]` | Unit, federated-equals-pooled, privacy and fault-injection tests (mock network) |
| `make data` | Regenerate the synthetic datasets with datavalgen |
| `make build IMAGE=<name>` | Build the image with the version from its metadata |
| `make push-local IMAGE=<name>` | Build and push to the dev network's registry |
| `make net-up [SCENARIO=...]` / `net-down` / `net-reset` / `net-status` | Manage the dev network |
| `make smoke IMAGE=<name>` | `push-local`, then run that image's example studies against the dev network and check the result envelopes |
| `make store-json IMAGE=<name>` | Regenerate `algorithm.json` |
| `make affected [BASE=<ref>]` | List the images affected by changes since `<ref>` (used by CI, §11.1) |

CI runs `lint`, `test`, `build` and `smoke` (on the `faulty` scenario as well as
`healthy`) on every PR.

---

## 7. Resilience and orchestration

### 7.1 Node-side envelope
Every federated function is wrapped with `@v6core.envelope.safe_federated`. It **never
raises** for data problems. It always returns:

```json
{
  "envelope_version": 1,
  "status": "ok | partial | error",
  "organization_id": 3,
  "result": { "...": "algorithm-specific" },
  "errors": [
    {"code": "MISSING_COLUMN", "scope": "column:age", "message": "Column 'age' not found"}
  ]
}
```

- Every federated result carries `organization_id`, including in iteration rounds.
- Errors are **scoped** (`node`, `column:<name>`, `statistic:<col>.<stat>`,
  `stratum:<label>`) so one bad column only knocks out that column.
- Node error codes (extend in `envelope.py` only): `INVALID_PARAM`, `MISSING_COLUMN`,
  `NON_NUMERIC`, `NON_BINARY`, `INVALID_VALUE` (negative count, non-positive exposure,
  ...), `EMPTY_AFTER_FILTER`, `BELOW_MIN_ROWS`, `BELOW_MIN_EVENTS`, `SUPPRESSED`,
  `NOT_SUBTASK`, `INTERNAL_ERROR`.
- Central-side codes: `TIMEOUT`, `NODE_FAILED`, `NO_RESULT`, `QUORUM_NOT_MET`,
  `RANK_DEFICIENT`, `SINGULAR_MATRIX`, `NOT_CONVERGED`, `NUMERICAL_FAILURE`,
  `TOO_FEW_OBSERVATIONS`.
- Unexpected exceptions become `INTERNAL_ERROR` with a message that contains no data
  values. pandas and numpy messages often quote individual values, so never pass them
  through as they are.

### 7.2 Fan-out (`v6core.orchestration`)
All central functions create subtasks **only** through `fan_out()`:

```python
outcomes = fan_out(client, method="local_glm_sums", kwargs=common_kwargs,
                   per_org_kwargs={org_id: {...}},   # optional, e.g. ADMM's per-site u/x_prev
                   organizations=org_ids, timeout_s=params.timeout_s)
# -> {org_id: Outcome(status="ok|error|timeout", envelope=..., reason=...)}
```

It must:
- poll with a **timeout**. Never call a bare `wait_for_results()`, which blocks forever on
  an organization without a running node.
- key results by `organization_id`, **never by list position**
- convert crashed runs, missing results and malformed envelopes into outcomes instead of
  exceptions
- send one subtask to all organizations when kwargs are shared. When kwargs differ per
  organization, create all the tasks first and then wait for them **concurrently**, never
  one after the other.
- leave an extension point for retrying once on transient failures (off by default)

### 7.3 Iterative algorithms (`v6core.iteration`)
- Participation is decided in the first phase. Later rounds only go to the organizations
  that qualified.
- The shared driver handles `max_iterations`, `tolerance`, NaN/Inf detection
  (`NUMERICAL_FAILURE`) and non-convergence (a warning, plus `converged: false` in the
  output).
- If an organization fails mid-iteration, behaviour follows the `on_node_failure` param:
  - `"abort"` (default): stop and report, because the estimand would silently change
  - `"restart_without"`: drop the organization and restart the iterations from scratch
- **Task budget.** Every round costs a vantage6 task cycle on every node. That's why
  IRLS (≈5–10 rounds) is the default and ADMM (tens to hundreds of rounds) is only used
  when a penalty requires it. Don't add extra per-round tasks such as evaluation (the
  legacy ADMM ran an evaluation task per site every round). Evaluate once, after
  convergence.
- Never silently "repair" a malformed node result (the legacy ADMM truncated or padded
  coefficient vectors). Treat it as that organization failing.

### 7.4 Central behaviour
- Validate **all** params before fanning out. Report every problem at once, not just the
  first one.
- Never index blindly (`results[0]`). Never assume every organization responded.
- The central function **returns** an error envelope for every expected failure and never
  raises (the legacy `average` raised `ValueError`, while the others returned
  `{"error": ...}`).

---

## 8. Privacy: nothing traceable to an individual

**Principle.** Sharing aggregated results is fine, both combined and per node. Nothing
that leaves a node may be traceable to an individual patient, either on its own or
combined with other released numbers (e.g. the model coefficients) or with outside
knowledge (e.g. someone knowing a patient's age and stage). Every rule below follows from
this. Everything is enforced **inside the image**, because we don't rely on node
configuration.

### 8.1 Never released (traceable)
| What | Why it's traceable | Do instead |
|---|---|---|
| Rows, IDs, per-patient outcomes, predictions or residuals, even without IDs | A prediction can be recomputed from the released coefficients and a patient's known covariates, then matched to reveal their outcome | Binned evaluation (§8.3) |
| Single-patient values: exact min/max, exact maximum follow-up, unique event times with frequency 1 | The value *is* one patient | Capped/rounded bounds. Binned time steps (`time_resolution`) |

**Accepted exception: `cox_regression`.** It keeps the legacy method, which shares each
node's exact unique event times and their frequencies. This is a deliberate decision
(§15). It's mitigated by `min_events`, the risk-set guard and the provenance guard. An
optional `time_resolution` parameter (default `null` = exact times, as in the legacy
method) lets a project bin the times when it wants to. Don't extend this exception to
other algorithms.
| Small counts (below the min cell count), including `row_count` after filters and labels of rare categories | A count of 1 plus outside knowledge identifies a person | Suppress. Merge rare labels into `"<other>"` |
| Any statistic computed on too few rows (sums, means, X'X, X'WX, gradients, local coefficients, accuracy) | With few rows, a sum or matrix can be solved back to individual values | Only release it when the node passes `min_rows` and rows/events-per-parameter floors |
| Two releases that differ by one patient | The difference is that patient (e.g. consecutive risk sets, two filters) | Risk-set guard **per node**, floors on every filtered stratum |
| Full-resolution curves (ROC, KM) | Each step is one patient | Binned curves (§8.3) |

### 8.2 Fine to share (when above the floors)
- Per-node aggregates and per-node results, e.g. local coefficients (ADMM), X'WX, sums,
  counts, per-site AUC from binned counts.
- Participation details: which organization was included or excluded, and why.
- Aggregate numbers in logs, as long as they would pass the same checks. Use
  `v6core.privacy.safe_log()`, which applies them. Never log individual values (e.g. the
  offending value in a non-binary column).

### 8.3 Federated model evaluation (`v6core.evaluation`)
- **AUC / ROC:** each node returns a histogram of predicted scores per outcome class on
  shared bins (default 100). Central combines the histograms and computes AUC and the ROC
  curve.
- **Calibration:** fixed probability bins. Per bin, the node returns n, Σpredicted and
  Σobserved, with small bins suppressed.
- **Recalibration slope/intercept:** a 2-parameter logistic regression of the outcome on
  the linear predictor, fitted through `v6core.glm`.
- **Accuracy, Brier score etc.:** per-node sums, combined centrally.

### 8.4 Mechanisms
- **Privacy thresholds are parameters with safe defaults.** `min_cell_count`,
  `min_rows`, `min_events`, `min_rows_per_parameter`, `min_events_per_parameter`,
  `max_categories` and `time_resolution` are normal request parameters (§9.1), because
  what's appropriate differs per project.
  - **Defaults** live in one place, `v6core.privacy.DEFAULTS`, and every image uses them.
    Starting values are the ones the legacy code used (cell count 5, `min_events` 10).
    Changing a default is a CHANGELOG entry.
  - **Absolute minimums** also live in `v6core.privacy` and are not configurable (e.g.
    `min_cell_count` ≥ 3, `min_rows` ≥ 5). A request below them is rejected with
    `INVALID_PARAM`. This stops settings like 0 or 1, which would make output traceable.
  - **Lowering a threshold below its default** is allowed down to the absolute minimum.
    It adds a warning, and the `privacy` block in the output records the values used and
    which ones were below default, so it's visible and auditable.
  - **The node enforces the thresholds it receives**, in the federated function.
    `central()` passes them on, and the provenance guard makes sure nobody can call node
    functions directly with different values.
- **Provenance guard on every federated function.** `v6core.provenance` checks that a
  federated call was created as a subtask by our own central function, building on the
  legacy Cox `ensure_spawned_by_central`. Without it, someone could call a node function
  directly with loosened settings and get traceable output. `safe_federated` applies it
  by default. Exempt a function explicitly where it makes sense (e.g. `data_check`). It
  relies on vantage6 internals (the container token, the task's parent field), so it
  lives in **one** place, has a dev-network test, and is re-verified on every vantage6
  upgrade. The mock-client exemption only lives in `v6core`.
- **Report it.** The central output's `privacy` block lists the effective thresholds and
  what was suppressed or excluded.
- **Optional, not default:** count rounding, and secondary suppression or deterministic
  noise keyed on a hash of the node's own dataset (never a key from the request).

Platform hardening (encryption, `share_algorithm_logs: false`) is recommended in the
README for production networks, but no algorithm may **depend** on it.

---

## 9. Parameters, outputs and the researcher experience

### 9.1 Standard parameter names
Use these exact names. The legacy column shows what to rename when porting.

| Concept | Standard name | Legacy names |
|---|---|---|
| Organizations to include (by name) | `organizations` | same |
| Quorum | `min_organizations` | same |
| Minimum usable rows per node | `min_rows` | same |
| Minimum events per node | `min_events` | `minimum_events` |
| Rows (or events) per parameter guard | `min_rows_per_parameter` / `min_events_per_parameter` | `max_pct_vars_vs_obs` (inverted percentage) |
| Covariates | `predictor_cols` | `feature_cols`, `predictor_cols`, `expl_vars` |
| Outcome (regression) | `outcome_col` | `target_col`, `outcome_col` |
| Outcome → 0/1 derivation | `outcome_representation` | `target_representation` |
| Survival time / event | `time_col`, `event_col`, `event_representation` | `outcome_col` (Cox), `outcome_representation` (Cox) |
| Poisson offset | `exposure_col` | same |
| Iteration limit / tolerance | `max_iterations`, `tolerance` | `n_rounds`, `num_rounds`, `max_iterations` |
| L1 penalty (logistic) | `l1_penalty` (default 0 = no penalty, IRLS) | `lambda_` |
| ADMM tuning (only used when `l1_penalty > 0`) | `admm_rho`, `admm_relaxation` | `rho`, `alpha` |
| Train/validation split | `train_ratio`, `seed` | same |
| Small-risk-set guard | `risk_set_min_change`, `max_held_event_fraction` | same |
| Privacy thresholds (§8.4) | `min_cell_count`, `max_categories`, `time_resolution` (plus `min_rows`, `min_events`, `min_*_per_parameter` above) | `suppress_threshold`, `step_days` (KM) |
| Common | `filters`, `group_by`, `timeout_s`, `on_node_failure`, `database` (default `"default"`) | — |

Each user-facing function has its own params model in `params.py`. That model is the
**single source of truth** for validation, README tables, `algorithm.json` and runner
validation.

### 9.2 Central result envelope

```json
{
  "status": "ok | partial | error",
  "algorithm": {"name": "poisson_regression", "version": "1.2.0", "v6core_version": "0.4.0"},
  "params": { "...": "fully resolved, defaults filled in" },
  "participation": [
    {"organization": "alpha", "status": "included"},
    {"organization": "beta",  "status": "excluded", "reason": "BELOW_MIN_EVENTS"},
    {"organization": "gamma", "status": "failed",   "reason": "TIMEOUT"}
  ],
  "result": { "...": "function-specific, see 9.3" },
  "warnings": ["..."],
  "errors": [{"code": "...", "scope": "...", "message": "..."}],
  "privacy": {"thresholds": {"min_cell_count": 5, "min_rows": 10, "min_events": 10},
              "below_default": [], "suppressed_cells": 3}
}
```

- `partial` means usable but incomplete (e.g. 1 of 4 columns failed, or 1 organization
  excluded). `participation` replaces the legacy `included_organizations` /
  `excluded_organizations` / `n_threshold_not_met`.
- Everything is JSON-safe: no numpy scalars, `NaN` → `null`. **Never put JSON strings
  inside JSON** (the legacy `"model": results.to_json()`).
- No rounding inside algorithms. The runner formats numbers for display.
- Counts that may be suppressed always have the same shape: `{"value": 42}` or
  `{"value": null, "suppressed": true}`.

### 9.3 Shared result shapes
Every regression model (linear, logistic, Poisson, Cox, ...) returns the same structure,
built by `v6core.inference`:

```json
"result": {
  "coefficients": [
    {"term": "age", "estimate": 0.031, "std_error": 0.008, "statistic": 3.9,
     "p_value": 0.0001, "ci_lower": 0.015, "ci_upper": 0.047,
     "exp_estimate": 1.031, "exp_ci_lower": 1.015, "exp_ci_upper": 1.048}
  ],
  "fit": {"method": "irls", "n_observations": 812, "n_events": 410, "df_residual": 807,
          "converged": true, "iterations": 6, "log_likelihood": -1234.5, "aic": 2479.0,
          "deviance": null, "null_deviance": null,
          "overall_test": {"type": "LR", "statistic": 31.2, "df": 4, "p_value": 1e-6},
          "model_specific": {"r_squared": null, "dispersion": null}},
  "evaluation": null
}
```

- `exp_*` fields are filled in for log/logit links and Cox, and are `null` otherwise.
- `statistic` is t for linear regression and z otherwise. The README says which.
- `evaluation`, when requested, holds the binned AUC/ROC/calibration from §8.3.
- Non-regression analyses (descriptive statistics, KM) define their own shape in their
  README. They still use the envelope and the suppressed-count shape.

### 9.4 Running algorithms: three ways, one contract
We do **not** build our own UI. Researchers use one of these three:

1. **`v6run` CLI** (the main route): `v6run validate study.yaml`,
   `v6run run study.yaml --out results/`, `v6run list`.
2. **Python API**: `from v6run import run` for notebooks.
3. **The vantage6 UI** (vantage6's own web interface), through **our own** algorithm
   store. Every image ships a checked `algorithm.json` with only the user-facing central
   function listed (federated functions are internal). The vantage6 UI turns it into a
   parameter form. Generate it with `make store-json`, which uses
   `v6 algorithm generate-store-json` if the pinned 4.x CLI has it and our own generator
   from the params model otherwise. The generator reads type hints and docstrings, so
   keep them accurate.

All three validate against the same params model **before** a task is created.

**This library is our own. Never publish to the public/community vantage6 algorithm
store.** Images are published to the GitHub Container Registry of this repo (§11.1). If we want UI forms, we run our own
algorithm store and link it to our collaborations. The dev network includes one, so this
can be tested.

**Runner installation:** the runner (`v6run`) is the small Python tool that replaces the
per-algorithm `run_study.py` scripts. A researcher writes a study file (§9.5) and runs
one command. The runner logs in, starts the task, waits with a timeout, and saves and
prints the results. Researchers install it straight from this public repo, pinned to a
release tag. No SSH key or package index is needed:
`pip install "git+https://github.com/<org>/<repo>.git@runner/v<semver>#subdirectory=runner"`.
The runner's README shows this command. The runner pulls in the matching
`vantage6-client` 4.x version.

### 9.5 Study file

```yaml
profile: dev                   # server/collaboration profile; `dev` = the local dev network
collaboration: lung-study
initiating_org: alpha
algorithm: logistic_regression
version: 1.2.0                 # required, never "latest"
organizations: [alpha, beta]   # optional; default = all
params:
  outcome_col: deadstatus.event
  predictor_cols: [age, clinical.T.Stage]
  evaluate: true
output: results/logreg
```

- **Credentials never go in study files or code** (dev-network fake credentials
  excepted). Use env vars, a keyring or a prompt, following grimoire's secrets policy.
- The runner writes `result.json` (the full envelope), `params.json`, a readable
  `summary.md`, and standard plots/tables (coefficient table, forest plot, KM curve,
  ROC/calibration). Plotting lives in the runner, **never** in the image. If researchers
  need a more readable result, extend the runner's report (e.g. a static HTML report).
  Don't build a web app.
- The runner prints participation and warnings prominently. A `partial` result must never
  look like a clean one.

---

## 10. Testing

All tests use the datavalgen profiles (§4).

1. **Federated equals pooled.** Run through vantage6's mock network/client and compare
   against a pooled reference on the concatenated data: statsmodels for linear/logistic
   (IRLS **and** ADMM with `l1_penalty=0`)/Poisson (incl. offset), lifelines for Cox/KM,
   pandas for descriptive statistics. Use tight tolerances on coefficients **and**
   standard errors.
2. **Evaluation.** Binned AUC is within a documented tolerance of the exact pooled AUC.
   Calibration bins match pooled bins.
3. **Fault injection.** One node `broken`, one `small`/`few_events`, one `empty`, one
   raising, one timing out, one returning a malformed envelope. Assert the result is
   `partial` with correct participation, or a clean `QUORUM_NOT_MET`. Never an unhandled
   exception, never a hang.
4. **Numerical edge cases.** `collinear` data gives `RANK_DEFICIENT`. `separation` and
   overflow give a clean `NUMERICAL_FAILURE` or a warning, never NaN coefficients
   presented as results. Non-convergence is reported.
5. **Privacy.**
   - No released count is below the threshold in effect.
   - Thresholds below the absolute minimums are rejected.
   - Thresholds below the default produce a warning and are recorded in `privacy`.
   - Calling a federated function directly (not as a subtask) returns `NOT_SUBTASK`
     (dev-network test).
   - **Canary test:** plant a unique sentinel value in one row, then assert it doesn't
     appear in any output, log or error message.
   - **No federated function returns anything whose size grows with the number of
     patients** (lists per row, per-patient predictions, unbinned event times). The
     only exception is `cox_regression`'s event-time table (§8.1).
6. **Envelope/schema tests.** Every output validates against the documented schema
   (§9.2, §9.3).
7. **Dev-network smoke test** (`make smoke`) on the `healthy` and `faulty` scenarios.

Every bug fix comes with a regression test.

---

## 11. Build, versioning, release

- Semantic versioning **per image**. A breaking change to params or output shape is a
  major bump. Record it in that image's `CHANGELOG.md`.
- Image: `ghcr.io/<org>/<repo>/<name>:<semver>` (GitHub Container Registry of this
  public repo, §11.1). Studies reference semver tags or digests, **never `latest`**. The
  output reports name, version and `v6core` version.
- `v6core` has its own version. Each image pins the `v6core` version it builds with. A
  `v6core` release doesn't force a rebuild of every image. Images adopt it in their own
  next release, and CI runs every image's tests against the newest `v6core` so breakage
  shows up early.
- **One Python version for all images**, taken from `versions.toml`. The legacy
  Dockerfiles mixed 3.10 and 3.12.
- Pin every dependency (lock file or hashes). Use the shared `docker/base.Dockerfile`.
  numpy/scipy/pandas cover every current method. Don't add torch or scikit-learn. If a
  future method truly needs a heavy dependency, record why in the README.
- Publish on tag only, after CI is green, including the smoke test.

### 11.1 CI/CD (GitHub Actions)
Workflows live in `.github/workflows/`. If grimoire prescribes a CI platform or shared
workflow templates, follow those and keep the same stages. Workflows call `make`
targets. They never duplicate build logic in YAML.

| Workflow | Trigger | Does |
|---|---|---|
| `ci.yml` | Every PR and push to `main` | `make lint`, `make test`. Builds **only the images affected** by the change (see below). Runs `make smoke` on the `healthy` and `faulty` scenarios for those images. Nothing is pushed. |
| `dev-images.yml` | Push to `main` | Builds the affected images and pushes them as `:sha-<short-sha>` to a separate dev path (`ghcr.io/<org>/<repo>/dev/<name>`). Lets you test unreleased versions on real test networks. Never used in studies for publication. |
| `release.yml` | Git tag `<name>/v<semver>` (e.g. `logistic_regression/v1.2.0`) | Checks that the tag matches the version in the image's metadata and that a CHANGELOG entry exists. Reruns tests and the smoke test for that image. Builds and pushes `ghcr.io/<org>/<repo>/<name>:<semver>`, then checks the image can be pulled **anonymously** (i.e. it's public). Records the **digest** in the GitHub release notes and attaches `algorithm.json` to the release. |
| `v6core-release.yml` | Git tag `v6core/v<semver>` | Tests `v6core` and creates a GitHub release. No package is published: images install `v6core` from the repo at build time. |
| `runner-release.yml` | Git tag `runner/v<semver>` | Tests the runner against the dev network and creates a GitHub release. Researchers install from that tag (§9.4). |
| `v6core-compat.yml` | Nightly + every `v6core` PR | Runs every image's tests against the newest `v6core`. Reports, never blocks other images. |

**Affected images.** A change under `algorithms/<name>/` affects that image. A change to
`packages/v6core/`, `docker/`, `versions.toml` or `datavalgen/schemas/` affects **all**
images. Compute this in one script (`make affected`), used by both `ci.yml` and
`dev-images.yml`.

**Rules for pushing images**
- Only `release.yml` pushes semver tags. Developers and agents never push release
  images from their machines.
- Semver tags are **immutable**. If a tag already exists in the registry, the workflow
  fails. Never overwrite one. Fix forward with a new patch version.
- No `latest` tag is pushed, anywhere.
- Images are built for `linux/amd64` (what our nodes run). Add other platforms only when
  a node needs them.
- **Registry: GitHub Container Registry (`ghcr.io`) of this public repo.** Workflows
  push with the built-in `GITHUB_TOKEN` (`permissions: packages: write`), so no extra
  secrets are needed. Use a `release` environment with required reviewers if grimoire
  asks for approval before publishing.
- **Images must be public**, so nodes can pull them without registry credentials in
  their node config (the zero-setup rule). New GHCR packages can start out private:
  when a package is first created, set its visibility to public in the package
  settings. `release.yml` fails if the anonymous pull check fails.
- **The only node setting** is allowing our images, e.g. `allowed_algorithms:
  ["^ghcr\.io/<org>/<repo>/.*"]`. The README for node admins gives this line.
- **The repo is public.** Besides synthetic data only (§1), that means no real server
  URLs, organization names from projects, credentials or internal hostnames in code,
  configs, examples or commit history.
- Each released image gets labels (OCI annotations) for the source commit, image
  version, `v6core` version and vantage6 version, so a running image can be traced back
  to its code.
- Optional hardening, when the registry supports it: vulnerability scan (fails on
  critical issues), SBOM, and image signing.

**After a release** (manual, until the store can be updated from CI):
1. If we run our own algorithm store: upload the attached `algorithm.json` there,
   referencing the image **by digest**. Never the public/community store.
2. Tell node admins the new image name + digest if their `allowed_algorithms` lists
   digests.
3. Update the version in `examples/studies/` for that image.

---

## 12. Coding conventions (on top of grimoire)

- No module-level side effects. No `np.random.seed(...)` at import (the legacy ADMM did
  this). Use `np.random.default_rng(seed)` passed down explicitly.
- Vectorise numerical code. No Python per-row loops in likelihoods or gradients (the
  legacy ADMM gradient looped over rows).
- Algorithm docstrings describe the **interface** (params, returns). Method derivations,
  privacy reasoning and design history go in the image's README. The legacy module
  docstrings of 50–120 lines should move there.
- Units are explicit params (`time_unit`). Don't hard-code "days".

---

## 13. Checklist: adding or changing an analysis

- [ ] Follows grimoire conventions.
- [ ] Is its own image (§3.4) with one user-facing central function and its own params
      model.
- [ ] Logic in `core.py` / `v6core`, no vantage6 imports there. Entrypoints are thin.
- [ ] Uses the `v6core` building blocks from §3.2 and re-implements none of them.
- [ ] Works on a stock node: no env vars, no node config. Column params have no defaults.
- [ ] Standard parameter names (§9.1) and output shapes (§9.2, §9.3).
- [ ] Federated functions wrapped with `safe_federated` (provenance guard on). Subtasks
      only via `fan_out()`. Quorum enforced.
- [ ] Nothing released is traceable to an individual (§8.1). Canary and output-size
      tests pass.
- [ ] Tests from §10, with any new data needs added as datavalgen schemas.
- [ ] Example study added under `examples/studies/`. `make smoke` passes on `healthy`
      and `faulty`.
- [ ] `algorithm.json` regenerated. README and CHANGELOG updated. Correct semver bump.

---

## 14. Legacy code: porting notes

Legacy algorithms: `average`, `fed_statistics`, `linear_regression`,
`logistic_regression` (FedAvg), `admm_logistic_regression`, `poisson_regression`,
`coxph`, `kaplan_meier`. Port them onto `v6core` one at a time.

**Where each one goes** (see the table in §3.4)
- `linear_regression`, `poisson_regression` → their own images, on `v6core.glm`.
- `admm_logistic_regression` → `logistic_regression` image, as the `l1_penalty > 0` path.
- `logistic_regression` (FedAvg) → **retired**, don't port.
- `average` → folded into `descriptive_statistics`.
- `coxph` → `cox_regression`. `kaplan_meier` stays `kaplan_meier`. Both share
  `v6core.survival`.

**Worth keeping (generalise into `v6core`)**
- Linear: rank check before solve, condition-number warning, duplicate-column and
  outcome-in-predictors validation, RSS from additive sums.
- Poisson: IRLS with offset and closed-form null deviance, LR test, dispersion warning.
  This is the template for `v6core.glm`.
- Cox: covariate standardisation with back-transform, the provenance guard, and the
  risk-set jump guard (to be applied per node as well).
- ADMM: Boyd primal/dual convergence criterion and the L1 z-update.
- The `representation` modes for binary outcomes.

**Cross-cutting issues (all or most files)**
- Helpers copied into every file (`_require_columns`, `_filter_organizations`,
  `_derive_binary`, `_safe_inverse`, `_build_results_table`).
- Project-specific column defaults (`"age"`, `"Survival.time"`, `"Clinical.N.Stage"` as a
  Poisson outcome, ...).
- A bare `wait_for_results()` everywhere. Organizations without a node hang the run.
- Inconsistent parameter names, error handling (raise vs `{"error"}` vs
  `{"status": ...}`) and output shapes, including JSON strings inside JSON.
- Guards (`min_rows`, risk-set guard, `max_pct_vars_vs_obs`) are only checked centrally,
  so per-node results computed on too few rows are still released. Move the floors to
  the node.
- `run_study.py` per algorithm, with hard-coded credentials, `:latest` images and
  encryption off. These become `runner/` + study YAML.
- Unpinned dependencies and mixed Python versions.

**Per algorithm**
- `average`: raises instead of returning an error envelope. No row floor on the local
  sum.
- `fed_statistics`:
  - One bad column fails the whole node.
  - `row_count` after filters and the labels of rare categories are released
    unsuppressed.
  - Exact min/max are released.
  - The secondary suppression key comes from the request.
- `admm_logistic_regression`:
  - `collect_predictions` sends per-patient outcomes and predictions to the server, and
    per-site ROC curves are returned at full resolution. Both are traceable. Replace them
    with `v6core.evaluation`.
  - Global `np.random.seed(67)` at import.
  - Evaluation tasks every round, and sequential per-site waits.
  - Silent truncation/padding of coefficient vectors.
  - Per-row Python gradient loop.
  - sklearn needed only for recalibration.
  - No standard errors.
- `coxph`:
  - The `minimum_events` check counts **non-null outcome rows, not events**
    (`df[outcome_col].notnull().sum()`), so nodes with few events still qualify. Fix
    this and add a test.
  - Phase 1 releases exact unique event times per node. **Kept by decision** (§8.1
    exception). Add the optional `time_resolution` parameter, defaulting to exact.
  - Port the method itself unchanged. That includes standardisation, the risk-set jump
    guard, inference, AIC and the overall test. Only the plumbing moves to `v6core`
    (envelope, fan-out, participation, standard names, result shape). The federated
    results must match the legacy `coxph` output on the same data. Add that as a
    regression test.
  - The provenance guard uses the private `client._access_token`. Isolate it in
    `v6core.provenance`.
- `linear_regression`: X'X/X'y have no node-level rows-per-parameter floor.
- `poisson_regression`: only clips `eta` instead of standardising covariates. Phase 1
  sums have no row floor.
- `kaplan_meier`:
  - The exact per-node maximum time is returned and logged. Bin or cap it.
  - A fresh noise seed each run is returned in the output.
  - The risk-set guard is central-only.

---

## 15. Open decisions (resolve these, then move the answers into the relevant sections)

- [x] **CI platform:** GitHub Actions, matching grimoire's own reference workflow
      (`coding/ci-workflow.yaml`). `.github/workflows/ci.yml` runs `make setup`,
      `make data`, `make lint`, `make test`, then `make build` for every image
      `make affected` reports changed — plain `docker build` works fine on a
      GitHub-hosted runner (Docker preinstalled), no special runner needed.
- [ ] **Docker-in-CI for `make smoke` specifically** is still open: standing up the
      full dev network (server, store, 3 nodes, 1 node-less org, a local registry) as
      a GitHub Actions job is a bigger undertaking (multi-container orchestration,
      resource/time limits on hosted runners, whether a self-hosted runner is needed)
      that wasn't investigated yet. `make smoke` has been run and verified manually
      against a live dev network for `descriptive_statistics` (both `healthy` and
      `faulty` scenarios); automating that in CI is tracked follow-up work, not
      something CI currently does.


