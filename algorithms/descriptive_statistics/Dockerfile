# Build context MUST be the repo root so packages/v6core can be installed into the
# image (AGENTS.md §2):
#   docker build -f algorithms/descriptive_statistics/Dockerfile -t descriptive_statistics:dev .
FROM mdw-v6-base:latest

WORKDIR /app
COPY packages/v6core /app/v6core
COPY algorithms/descriptive_statistics /app/descriptive_statistics

# --no-deps: every dependency is already pinned in the base image; this only
# installs the two local packages themselves.
RUN pip install --no-cache-dir --no-deps /app/v6core /app/descriptive_statistics

ENV PKG_NAME=descriptive_statistics
CMD ["python", "-c", "from vantage6.algorithm.tools.wrap import wrap_algorithm; wrap_algorithm()"]
