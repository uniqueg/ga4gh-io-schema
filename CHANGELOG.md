<!--
SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>

SPDX-License-Identifier: Apache-2.0
-->

# Changelog

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
- The profile is cut back to its core use (forms, run requests, outputs),
  and the meta-schema rejects what was removed. The
  [roadmap](docs/roadmap.md#scope-of-version-03) gives the reasons and lists
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
  `"type": "object"` if it sets `type`. It stays optional, as since
  version 0.1; without it, a schema now explicitly describes no outputs.
  (#11)

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
- Shared conventions of all subcommands: input from a path or `-` (standard
  input), `--output` for the result, `--json` for results and errors as JSON
  objects. (#9)
- A CLI reference in the documentation, generated from the parser. (#9)
