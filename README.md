# mdw-v6-algorithms

Standard, reusable vantage6 algorithms for MDW projects. One image version works for
every project without being rebuilt or edited — project-specific details (column
names, outcome coding, thresholds) are request parameters, never code or node config.

See [`AGENTS.md`](AGENTS.md) for the full design: architecture, privacy guarantees,
parameter/output conventions, testing, and the release process. This file is the
quick-start for researchers and contributors.

## What's available

| Image | Status | Method |
|---|---|---|
| `descriptive_statistics` | done | Per-node sufficient statistics, combined centrally to the exact pooled value |
| `linear_regression` | not yet ported | `v6core.glm`, gaussian family |
| `logistic_regression` | not yet ported | `v6core.glm`, binomial family (+ ADMM when `l1_penalty > 0`) |
| `poisson_regression` | not yet ported | `v6core.glm`, poisson family |
| `kaplan_meier` | not yet ported | Binned risk/event counts |
| `cox_regression` | not yet ported | Pooled Newton-Raphson (ported as-is from the legacy `coxph`) |

## Quick start

```bash
make setup                                   # install everything (uv sync)
make data                                    # generate the synthetic test datasets
make test                                    # unit + mock-network tests
make net-up                                  # bring up the local dev network (SCENARIO=healthy by default)
make push-local IMAGE=descriptive_statistics # build and push an image to the dev network's registry
uv run v6run run examples/studies/descriptive_statistics.yaml
make smoke IMAGE=descriptive_statistics      # push-local, then run that image's example studies and check the envelopes
make net-down
```

Researchers running a study (not developing algorithms) only need `v6run` — see
[`runner/README.md`](runner/README.md) — and a study file like
[`examples/studies/descriptive_statistics.yaml`](examples/studies/descriptive_statistics.yaml).

## Repository layout

```
packages/v6core/     # shared building blocks every algorithm is built on
algorithms/<name>/   # one image per analysis: core.py (pure) + entrypoints.py (vantage6 shell)
runner/              # v6run: the CLI/Python API researchers use to run a study
dev-network/         # local vantage6 network for testing images end to end
datavalgen/          # synthetic test-data schemas and generated profiles
examples/studies/    # example study files, all runnable against the dev network
docker/              # the shared base image every algorithm image builds from
```

## Status / known gaps

- Only `descriptive_statistics` is ported so far; the other five images in the table
  above are tracked follow-up work.
- The dev network's algorithm store couldn't be validated in every environment (see
  [`dev-network/README.md`](dev-network/README.md)) — the rest of the network (server,
  UI, nodes, local registry) doesn't depend on it and has been fully validated,
  including against a real vantage6 node (not just the mock client).
- `make store-json` (regenerating `algorithm.json` from an algorithm's params model)
  isn't implemented yet; `descriptive_statistics/algorithm.json` is hand-written.
- Standing up the dev network inside CI (`make smoke` automated, not just run
  manually) is open — see AGENTS.md §15.
