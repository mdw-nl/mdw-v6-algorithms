.PHONY: setup lint test data build push-local net-up net-down net-reset net-status smoke store-json affected

IMAGE ?=
SCENARIO ?= healthy
BASE ?= main

setup:
	uv sync

lint:
	uv run ruff format --check .
	uv run ruff check .
	uv run ty check .

# make test [IMAGE=<name>]  -- IMAGE scopes to algorithms/<name>'s own tests;
# omit it to run the whole suite (v6core + every algorithm + the runner).
test:
	@if [ -n "$(IMAGE)" ]; then \
		uv run pytest algorithms/$(IMAGE)/tests -q; \
	else \
		uv run pytest -q; \
	fi

data:
	uv run python datavalgen/generate_profiles.py

# make build IMAGE=<name>  -- builds the shared base image first (cheap/cached
# after the first run), then the algorithm image from the repo root so
# packages/v6core is in the build context (AGENTS.md §2).
build:
	@test -n "$(IMAGE)" || (echo "Usage: make build IMAGE=<name>" >&2; exit 1)
	docker build -f docker/base.Dockerfile -t mdw-v6-base:latest .
	docker build -f algorithms/$(IMAGE)/Dockerfile -t $(IMAGE):dev .

push-local: build
	bash dev-network/scripts/push_image.sh $(IMAGE) dev

net-up:
	SCENARIO=$(SCENARIO) bash dev-network/scripts/up.sh

net-down:
	bash dev-network/scripts/down.sh

net-reset:
	SCENARIO=$(SCENARIO) bash dev-network/scripts/reset.sh

net-status:
	bash dev-network/scripts/status.sh

# make smoke IMAGE=<name>  -- push the locally built image, then run every study
# under examples/studies/ whose `algorithm` matches it, and fail if any run isn't
# at least `partial` (AGENTS.md §6: "push-local, then run that image's example
# studies against the dev network and check the result envelopes").
smoke: push-local
	@test -n "$(IMAGE)" || (echo "Usage: make smoke IMAGE=<name>" >&2; exit 1)
	uv run python dev-network/scripts/smoke.py $(IMAGE)

store-json:
	@test -n "$(IMAGE)" || (echo "Usage: make store-json IMAGE=<name>" >&2; exit 1)
	@echo "TODO: generate algorithms/$(IMAGE)/algorithm.json from its params model (not yet implemented)."

# make affected [BASE=<ref>]  -- images touched since BASE, or affected indirectly
# by a change to packages/v6core, docker/, versions.toml or datavalgen/schemas/
# (AGENTS.md §11.1). Used by CI.
affected:
	@changed=$$(git diff --name-only $(BASE)...HEAD); \
	if echo "$$changed" | grep -qE '^(packages/v6core/|docker/|versions\.toml|datavalgen/schemas/)'; then \
		ls algorithms | grep -v '^README'; \
	else \
		echo "$$changed" | grep -oE '^algorithms/[^/]+' | sed 's#algorithms/##' | sort -u; \
	fi
