#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0
#
# The demo with TRS-Filer (docs/adoption/demo-trs-filer.md): starts
# TRS-Filer locally with Docker Compose (without authentication, on the
# loopback interface only), registers the demo workflow with its I/O Schema
# as a file of type IO_SCHEMA, finds the schema as a client and builds the
# WES run request; then stops TRS-Filer and removes its data.
#
# Environment:
#   TRS_FILER_DIR     checkout of elixir-cloud-aai/trs-filer (required)
#   TRS_FILER_PORT    port on 127.0.0.1 (default: 8080)
#   SCHEMA_FILE_TYPE  IO_SCHEMA (default) or OTHER
#   REVISION          commit of this repository that the URL of the primary
#                     descriptor pins (default: HEAD)
#   PYTHON            Python with this package installed (default: python)
#   KEEP              1 to leave TRS-Filer running

set -euo pipefail

: "${TRS_FILER_DIR:?set TRS_FILER_DIR to a checkout of elixir-cloud-aai/trs-filer}"
port="${TRS_FILER_PORT:-8080}"
python="${PYTHON:-python}"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "${here}/../.." && pwd)"
revision="${REVISION:-$(git -C "${root}" rev-parse HEAD)}"
trs_url="http://127.0.0.1:${port}/ga4gh/trs/v2"

# The port of the demo, in place of TRS-Filer's 8080, and a project and an
# image name of its own, so that other Compose projects of the checkout, and
# their image, are left alone
override="$(mktemp)"
printf 'services:\n  trs-filer:\n    image: io-schema-trs-filer-demo:local\n    ports: !override\n      - "127.0.0.1:%s:8080"\n' \
  "${port}" > "${override}"
compose=(docker compose --project-name io-schema-trs-filer-demo
  --project-directory "${TRS_FILER_DIR}"
  -f "${TRS_FILER_DIR}/docker-compose.yaml" -f "${override}")
cleanup() {
  if [[ "${KEEP:-0}" != 1 ]]; then
    "${compose[@]}" down --volumes >&2
  fi
  rm -f "${override}"
}
trap cleanup EXIT

# Writes without authentication: for local development only (see "Running
# without authentication" in TRS-Filer's docs/development.md)
TRS_FILER_CONFIG_OVERLAY=/etc/trs-filer/config.dev.yaml:/etc/trs-filer/config.noauth.yaml \
  "${compose[@]}" up --detach --build --wait --wait-timeout 300 >&2

echo "== Register the demo workflow (I/O Schema of type ${SCHEMA_FILE_TYPE:-IO_SCHEMA})" >&2
"${python}" "${here}/register.py" --trs-url "${trs_url}" --revision "${revision}" \
  --schema-file-type "${SCHEMA_FILE_TYPE:-IO_SCHEMA}" >&2

echo "== Find the I/O Schema as a client and build the run request" >&2
"${python}" "${here}/trs_client.py" --trs-url "${trs_url}"
