# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

# One image for the parts of the prototype (a proof of concept, not a
# product): the host of the form and the TRS stub. Build it from the root of
# the repository (see compose.yaml); .dockerignore keeps the context to the
# files below. Both images are pinned to digests, which Dependabot updates
# (`.github/dependabot.yml`).

# uv, which installs the versions of `uv.lock`, as CI does; only mounted
# while installing, so that it doesn't end up in the image
FROM ghcr.io/astral-sh/uv:0.13.9@sha256:d3b601f0c7b118bc1753febf7c41cc80981df678445e0254284eecf84db79a7d AS uv

FROM python:3.15-alpine@sha256:0f9552bb28711333da16915ec146f5e6bb44a7fdac9ced15dc17c2e0206346dd

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_NO_CACHE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH

WORKDIR /app

# The package, for the host (validator and request builder), with the
# runtime dependencies at the versions of `uv.lock` (no extras); the build
# fails if the lock doesn't match `pyproject.toml`
COPY pyproject.toml uv.lock README.md ./
COPY LICENSES LICENSES
COPY schemas schemas
COPY src src
RUN --mount=from=uv,source=/uv,target=/usr/local/bin/uv \
    uv sync --locked --no-dev --no-editable --python /usr/local/bin/python3

# The demo workflow (served by the stub) and the prototype
COPY examples/demo examples/demo
COPY prototype prototype

USER 65534:65534

CMD ["python", "prototype/host/form_host.py", "--host", "0.0.0.0"]
