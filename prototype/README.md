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
| `trs-stub/` | A TRS v2 stub that serves the end-to-end demo (`examples/demo/`) and its IO schema from files, with no database. |

How to run each part, and what it does and doesn't implement:
[Prototype](https://ga4gh-io-schema.readthedocs.io/en/latest/adoption/prototype/)
(`docs/adoption/prototype.md`).
