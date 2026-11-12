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
- Files and directories are file references: strings with the new
  `x-ga4gh-file` annotation, which the meta-schema checks. `x-ga4gh-drs-uri`
  is removed; `"schemes": ["drs"]` of the annotation replaces it. Schemas with
  `x-ga4gh-file` can't have `format` (e.g., `uri`, which rejects compact DRS
  identifiers) or `contentMediaType`, which described the string, not the
  referenced file; the media type goes into `mediaType` of the annotation.
  (#10)

### Added

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
