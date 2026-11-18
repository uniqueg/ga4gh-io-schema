<!--
SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>

SPDX-License-Identifier: Apache-2.0
-->

# Prototype

A proof of concept, not a product: the parts that show, on a single laptop
and without outside services, that an IO schema is enough to get from a
workflow in a tool registry to a WES run request. They aren't maintained
like the `ga4gh-io-schema` package and aren't for deployment.

| Directory | What it is |
| --- | --- |
| `trs-stub/` | A TRS v2 stub that serves the end-to-end demo (`examples/demo/`), the seeded workflows (`examples/workflows/`) and their IO schemas from files, with no database. |
| `host/` | The host of the form: users pick a workflow in TRS, fill in the form of its IO schema and see the WES run request (or send it to a WES). |
| `Dockerfile`, `compose.yaml` | Both parts in one small image, started with `make demo` (in the root of the repository; it sets `TRS_URL` and `WES_URL` empty, for the local stub and no WES) or `docker compose -f prototype/compose.yaml up --detach --build --wait`; then open <http://127.0.0.1:8000/>. |

How to run each part, and what it does and doesn't implement:
[Prototype](https://ga4gh-io-schema.readthedocs.io/en/latest/adoption/prototype/)
(`docs/adoption/prototype.md`).
