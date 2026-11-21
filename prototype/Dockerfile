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

FROM python:3.13-alpine@sha256:9ef1a599f863231c3d91e941389bfdc4a2d6070557243d54df1a4e57015b960e

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

# COPY keeps the modes of the checkout, and a clone made with a strict umask
# (e.g., 077) has files that only their owner can read, which the user below
# couldn't open: everything copied becomes readable for all and writable only
# by root, directories searchable. A step of its own rather than `COPY
# --chmod`, whose symbolic modes older Docker versions (Dockerfile frontend
# before 1.14) reject or ignore; keep it after the last COPY
RUN chmod -R u=rwX,go=rX /app

USER 65534:65534

CMD ["python", "prototype/host/form_host.py", "--host", "0.0.0.0"]
