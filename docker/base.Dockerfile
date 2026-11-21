# Shared pinned base image for every algorithm (AGENTS.md §2, §11). A version bump
# here is one place, not one per algorithm.
#
# Build: docker build -f docker/base.Dockerfile -t mdw-v6-base:latest .
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Pinned to versions.toml. numpy/scipy/pandas cover every current method; no
# torch or scikit-learn (AGENTS.md §11).
RUN pip install --no-cache-dir \
    "vantage6-algorithm-tools==4.14.0" \
    "pandas>=2.2.0,<3" \
    "numpy>=1.26.0" \
    "scipy>=1.12.0" \
    "pydantic>=2.6.0" \
    "pyjwt>=2.8.0" \
    hatchling
