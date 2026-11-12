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

### Added

- Shared conventions of all subcommands: input from a path or `-` (standard
  input), `--output` for the result, `--json` for results and errors as JSON
  objects. (#9)
- A CLI reference in the documentation, generated from the parser. (#9)
