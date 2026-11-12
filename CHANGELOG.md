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
- `x-ga4gh-drs-uri` is removed; `"schemes": ["drs"]` of the new
  `x-ga4gh-file` annotation replaces it. (#10)
- Files and directories are file references (`x-ga4gh-file`), no longer
  strings with `"format": "uri"` and `contentMediaType`. A file reference is
  a flat string schema: no `format` (`uri` rejects compact DRS identifiers),
  no `contentMediaType`, `contentEncoding` or `contentSchema` (they describe
  the string, not the referenced file; the media type goes into `mediaType`),
  and no in-place applicators such as `allOf` (the meta-schema checks the
  annotated schema; schemas around it must not add these keywords either).
  (#10)
- The format of a file is named by `ontology` of the file reference;
  `x-ga4gh-ontology` names the data of a parameter (e.g., an EDAM data
  term), no longer also the format. (#10)
- The `$id` of an IO schema, if present, must be an absolute URI and not the
  URL of a branch at GitHub or GitLab. (#12)
- The profile is cut back to its core use (forms, run requests, outputs),
  and the meta-schema rejects what was removed. The
  [roadmap](https://ga4gh-io-schema.readthedocs.io/en/latest/roadmap/#scope-of-version-03) gives the reasons and lists
  what is deferred. (#17)
  - `x-ga4gh-fa-icon` is removed (cut); schemas that use it no longer
    validate.
  - The `rst` value of `x-ga4gh-description-format` is removed (cut); use
    `markdown` or `plain_text`.
  - The `password` widget is removed (cut): workflow parameters are not a
    channel for secrets.
  - The viewers `genome-browser`, `scatter-plot`, `pdf-viewer` and
    `markdown-viewer` are removed from the vocabulary of UI widgets
    (deferred); `table-viewer`, `html-viewer` and download remain.
  - `x-ga4gh-tabular-schema` is experimental and only a hint for clients;
    validation of tabular files is deferred.
  - Servers no longer accept IO schemas supplied by clients in a run request
    (cut); they use schemas from trusted sources only.
  - The proposed TRS file type `IO_SCHEMA` is deferred; IO schemas are
    published as TRS files of type `OTHER`.
  - The proposal no longer covers chaining workflows by ontology terms
    (deferred), drafting of IO schemas by AI agents (cut), or the claim that
    the profile suits machine learning pipelines (cut; an open question on
    the roadmap).
- `outputs` must be an object schema (not a boolean schema), with
  `"type": "object"` if it sets `type`, and without references or
  applicators (`$ref`, `$dynamicRef`, `allOf`, `anyOf`, `oneOf`, `not`,
  `if`, `then`, `else`, `dependentSchemas`) on `outputs` itself: the
  outputs are its direct `properties`. Schemas that keep their outputs
  behind a `$ref` inline the referenced schema. `x-ga4gh-output-glob`
  needs a list's `items` written in place, not as a `$ref`. `outputs`
  stays optional, as since version 0.1; without it, a schema now
  explicitly describes no outputs. (#11)

### Added

- An outputs model: the shapes of output values (files, lists, files keyed
  by sample, records, scalars; absent, never `null`, if not produced), the
  normalised outputs object that clients consume, how outputs are found in
  what WES servers report (by name, else by glob), partial outputs of
  failed runs, and notes on CWL, WDL, Nextflow and Snakemake. The new
  keyword `x-ga4gh-output-glob` finds an output among the files of a run,
  relative to its output directory, for engines that don't report outputs
  by name. The examples have more outputs. (#11)
- File references (`x-ga4gh-file`): kind (`file` or `directory`), media
  type, format term, compression, required secondary files as CWL-style
  suffix patterns, and allowed URI schemes; a defined value syntax (absolute
  URIs, including compact DRS identifiers, and paths for inputs only); a
  specification page with the mapping to CWL, WDL and nf-schema. The
  examples use them, and their inputs reject unknown and missing values
  (`required`, `additionalProperties: false`). (#10)
- Identity and engine binding: the top-level keyword `x-ga4gh-workflow` ties
  an IO schema to a TRS tool version and its engine (TRS ids, descriptor
  type and version, path and checksum of the primary descriptor, entry
  point; the entry point is required for WDL), and `x-ga4gh-parameter` binds
  a parameter to the engine's parameter name and type. New vocabulary files
  `workflow.schema.json` and `parameter.schema.json`; new page "Identity and
  engine binding" with the rules for `$id`s and for drift. (#12)
- A convention for publishing IO schemas in TRS without a change of TRS:
  file type `OTHER`, path `ga4gh-io.schema.json` next to the primary
  descriptor, identified by `$schema`; an `IO_SCHEMA` file type is deferred.
  (#12)
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
- A JavaScript runner of the conformance suite and the examples
  (`tests/js/`, run in CI) with Ajv and @hyperjump/json-schema, and a page
  "JavaScript validators" on how to set them up. (#36)

### Fixed

- The meta-schema works with JavaScript validators: the rules of
  `$defs/node` reach nested schemas through explicit `$ref`s
  (`$defs/node/$defs/subschemas`) instead of `$dynamicAnchor`, which Ajv
  supports only at the root of a schema. Ajv accepted schemas that broke
  the rules for nested schemas (e.g., unknown widgets, bad file
  references). The results of the Python validator are unchanged. (#36)

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
  mandate"); its meta-schema didn't enforce that (it required a top-level
  `inputs` property, not the `properties` wrapper of the examples).
  Version 0.2 drops the mandate: `outputs` is optional.
- **Scope reversal, WES:** version 0.1 listed changes to the WES API as out
  of scope, and said that WES servers *should* validate requests and
  *should* answer failures with `HTTP 400`. Version 0.2 says that WES APIs
  *must* return `HTTP 400` when validation on the server fails, that the
  error *should* name the path of the error, and that the schema's
  `x-ga4gh-error-message` *should* be preferred to the message of the
  validator. Version 0.3 keeps validation optional for WES
  servers, needs no change of the WES API, and states the requirements for
  servers that validate in the conformance class
  [WES server](https://ga4gh-io-schema.readthedocs.io/en/latest/specification/conformance/#wes-server).
- The meta-schema names the ontology term `x-ga4gh-ontology`, as the text
  of version 0.1 did; the meta-schema of version 0.1 called it
  `x-ga4gh-format`.

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
  wrapper and the keywords `x-ga4gh-drs-uri`, `x-ga4gh-ontology` (called
  `x-ga4gh-format` in the meta-schema),
  `x-ga4gh-ui-widget`, `x-ga4gh-tabular-schema`, `x-ga4gh-fa-icon`,
  `x-ga4gh-description-format`, `x-ga4gh-hidden` and
  `x-ga4gh-error-message`, with a vocabulary of UI widgets.
- A proposed TRS file type for IO schemas, validation on WES and TES
  servers, and packaging of IO schemas in Workflow RO-Crates.
- The claim that the profile suits machine learning workloads (e.g.,
  hyperparameters and model artefacts).
- The meta-schema and a Python validator (`ga4gh-io-schema-validator`).

<!-- --8<-- [end:changes] -->
