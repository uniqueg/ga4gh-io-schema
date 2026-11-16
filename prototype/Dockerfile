# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

# One image for the parts of the prototype (a proof of concept, not a
# product): the host of the form and the TRS stub. Build it from the root of
# the repository (see compose.yaml); .dockerignore keeps the context to the
# files below.
FROM python:3.13-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# The package, for the host (validator and request builder)
COPY pyproject.toml README.md LICENSE ./
COPY LICENSES LICENSES
COPY schemas schemas
COPY src src
RUN pip install .

# The demo workflow (served by the stub) and the prototype
COPY examples/demo examples/demo
COPY prototype prototype

USER 65534:65534

CMD ["python", "prototype/host/form_host.py", "--host", "0.0.0.0"]
