<!--
SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>

SPDX-License-Identifier: Apache-2.0
-->

# Changelog

<!-- --8<-- [start:changes] -->
Notable changes of the profile and the `ga4gh-io-schema` package. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Breaking changes

- The command-line tools are subcommands of one command, `ga4gh-io-schema`:
  `ga4gh-io-schema validate` replaces `ga4gh-io-schema-validator`, which is
  removed without an alias. The exit status now tells failures apart (1: the
  schema doesn't comply, 2: wrong arguments, 3: a file can't be read, isn't
  valid JSON, or the meta-schema is malformed or has references that can't
  be resolved, 4: unexpected errors); before,
  all failures exited with 1. (#9)

### Added

- Shared conventions of all subcommands: input from a path or `-` (standard
  input), `--output` for the result, `--json` for results and errors as JSON
  objects. (#9)
- A CLI reference in the documentation, generated from the parser. (#9)
- Conformance: BCP 14 (RFC 2119, RFC 8174) key words, used consistently in
  the normative text; conformance classes (Schema document, Validator,
  Producer, Form renderer, Request builder, Output normaliser, WES server)
  with their requirements; a table of implementations. (#14)
- A language-neutral conformance suite in `tests/conformance/` (the
  positive and negative schema documents of the tests, moved from
  `tests/data/`), with a runner for this package. (#14)
- Versioning policy and governance note, and this changelog in the
  documentation, with the history of versions 0.1 and 0.2. (#14)

## v0.2 (2026-10-13)

Draft of the proposal; not released (no tag).

### Breaking changes

- The profile is an interface description of workflows and workflow
  components, no longer of tool executables in general: bare tasks of the
  GA4GH Task Execution Service (TES) are out of scope, and standalone tools
  are covered only when wrapped as workflow units (e.g., a CWL
  `CommandLineTool` or an nf-core module). Version 0.1 targeted both WES
  and TES.
- **Scope reversal, outputs:** the text of version 0.1 required every
  schema to define both `inputs` and `outputs` (the "bi-directional
  mandate"), although its meta-schema required only `inputs`. Version 0.2
  drops the mandate: `outputs` is optional.
- **Scope reversal, WES:** version 0.1 listed changes to the WES API as out
  of scope, and said that WES servers *should* validate requests and
  *should* answer failures with `HTTP 400`. Version 0.2 says that WES APIs
  *must* return `HTTP 400` with the path of the error when validation on
  the server fails, and *should* return the schema's
  `x-ga4gh-error-message`. Version 0.3 keeps validation optional for WES
  servers, needs no change of the WES API, and states the requirements for
  servers that validate in the conformance class
  [WES server](https://ga4gh-io-schema.readthedocs.io/en/latest/specification/conformance/#wes-server).
- `x-ga4gh-format`, the ontology term of a file's type, is replaced by
  `x-ga4gh-ontology`, an ontology term of any input or output.

### Added

- Rules for native JSON Schema keywords instead of custom ones: file
  references as `{"type": "string", "format": "uri"}`, `contentMediaType`
  for media types, `uniqueItems` for unique array items.
- The relation of each `x-ga4gh-*` keyword to nf-schema.
- Roles for tabular data: clients use `x-ga4gh-tabular-schema` as a hint
  for forms; the execution side validates the files.
- The output contract: clients match the keys of `outputs` with the
  outputs of the WES run log.
- Integration with the Workflow Run RO-Crate profiles.
- The claim of version 0.1 that the profile suits machine learning
  workloads is widened: the profile is called domain-agnostic. (Version 0.3
  cuts both claims, see
  [Open questions](https://ga4gh-io-schema.readthedocs.io/en/latest/roadmap/#open-questions).)

## v0.1 (2026-10-10)

Initial draft of the proposal; not released (no tag).

### Added

- Ecosystem survey of how workflow languages and platforms describe inputs
  and outputs, and the case for a JSON Schema profile.
- The JSON Schema (Draft 2020-12) profile with an `inputs`/`outputs`
  wrapper and the keywords `x-ga4gh-drs-uri`, `x-ga4gh-format`,
  `x-ga4gh-ui-widget`, `x-ga4gh-tabular-schema`, `x-ga4gh-fa-icon`,
  `x-ga4gh-description-format`, `x-ga4gh-hidden` and
  `x-ga4gh-error-message`, with a vocabulary of UI widgets.
- A proposed TRS file type for IO schemas, validation on WES and TES
  servers, and packaging of IO schemas in Workflow RO-Crates.
- The claim that the profile suits machine learning workloads (e.g.,
  hyperparameters and model artefacts).
- The meta-schema and a Python validator (`ga4gh-io-schema-validator`).

<!-- --8<-- [end:changes] -->
