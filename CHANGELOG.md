<!--
SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>

SPDX-License-Identifier: Apache-2.0
-->

# Changelog

<!-- --8<-- [start:changes] -->
Notable changes of the profile and the `ga4gh-io-schema` package. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

Version 0.3 of the profile; not released (no tag). Releases come with the
move of the repository to GA4GH; until then, pin a commit SHA (see
[Development](https://ga4gh-io-schema.readthedocs.io/en/latest/development/#schema-identifiers)).

### Breaking changes

- The `$id`s of the meta-schema and its vocabularies, and with them the
  `$schema` of IO schemas, start with
  `https://raw.githubusercontent.com/elixir-cloud-aai/ga4gh-io-schema/main/schemas/`
  instead of `https://raw.githubusercontent.com/uniqueg/ga4gh-io-schema/main/schemas/`,
  because the repository moves to elixir-cloud-aai. A stable identifier
  follows later (#26). To migrate, change `$schema` in your IO schemas.
  (#77)
- `ga4gh-io-schema validate` and `validate_schema()` always validate
  against the profile that the package ships, and reject a schema whose
  `$schema` is missing or names another meta-schema (e.g., plain JSON
  Schema); before, they validated against whatever `$schema` named. With
  `--meta-schema` (`meta_schema=`), the schema's `$schema` must name the
  `$id` of that meta-schema, if it has one; before, `$schema` was ignored.
  To migrate, set `$schema` to the `$id` of the profile, or pass the
  meta-schema that your schemas name. (#109)
- The meta-schema no longer requires `$schema` (it still checks its
  value): clients and meta-schemas that apply only the profile's
  meta-schema, without the Python validator, must now check that `$schema`
  is there themselves (see "Fixed", #61). (#109)

- Widgets of `x-ga4gh-ui-widget` must fit their schema: the meta-schema
  rejects, for example, a `slider` without a numeric type and both bounds, a
  `date-picker` without `"format": "date"`, a `file-picker` without
  `x-ga4gh-file`, `tags` on anything but an array of strings, and output
  viewers on the parameters of `inputs` (and input widgets on `outputs`).
  To migrate, add the `type` and keywords that the widget needs next to it
  (not only behind a `$ref`), or remove the widget. (#38)
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

- A check of the workflow block for clients:
  `ga4gh_io_schema.workflow.check_workflow()` and
  `ga4gh-io-schema verify` compare `trs_tool_id`, `trs_version_id` and
  `descriptor_type` of `x-ga4gh-workflow` with the tool version that a
  schema was fetched for, and its `checksum` with the checksums of the
  primary descriptor, from TRS (`FileWrapper.checksum`) or computed over
  its content; they return the mismatches and whether the schema is
  verified (step 2 of the guide for portals). `--require-verified` also
  fails on a schema whose checksum can't be compared. The form host of the
  prototype uses it and now also rejects schemas whose checksum doesn't
  match the primary descriptor. (#85)
- A TRS stub for the laptop prototype in `prototype/trs-stub/`, documented
  on the page "Prototype": it serves the end-to-end demo and its IO schema
  over the read-only TRS v2 endpoints that a client needs, from files in
  the repository, with no database. (#70)
- A proof of concept of a form in `prototype/host/`, documented on the page
  "Form proof of concept". A plain web component renders the inputs of an
  IO schema. A small Python host (`python prototype/host/form_host.py`)
  validates the values with the schema's error messages and shows the
  `workflow_params`. (#63)
- The host of the form proof of concept is part of the prototype and moved
  from `examples/form/` to `prototype/host/`. It shows the complete WES run
  request instead of only the `workflow_params`, with the `workflow_url` in
  TRS (`--trs-url`), and, given a WES (`--wes-url`), submits the request on
  request of the user and shows the run id and state. (#71)
- The prototype runs with Docker Compose (`docker compose -f
  prototype/compose.yaml up --build`): the TRS stub and the host, whose
  users pick a workflow from a TRS (`--trs-url`), fill in the form of its
  IO schema and see the WES run request. CI's job "End-to-end test" runs
  the stack and checks this path over the host's API and in a browser
  (Playwright; extra `e2e`). The host now answers `GET /api/...` only
  under its own names, like `POST`, and takes an empty `--wes-url` as
  none. Documented on the page "Prototype". (#72)
- An end-to-end demo in `examples/demo/`, documented on the page
  "End-to-end demo": a small WDL workflow with public test data, its IO
  schema generated by `convert wdl` (with a checked-in overlay, and a test
  that regenerates it), a script that registers both in TRS-Filer, and a
  script that turns a request of `wes-params --request` into one for
  Conquest, submits it, waits for the run and normalises its outputs. (#24)
- A guide for portals and clients: the steps from fetching an IO schema in
  TRS to handing the values to a request builder, the rendering of unions
  with a file reference (CWL `[File, string]`) and of hidden inputs that
  must be set, and corrected notes on form libraries (Ajv needs
  `strictSchema: false` and `'unsafe-eval'`; validators must not fetch
  references). (#39)
- A specification page "UI widgets": for each widget of the vocabulary, the
  types and keywords that it needs and the value that it produces; input
  widgets and output viewers kept apart. (#38)
- `ga4gh-io-schema convert nextflow`: converts an nf-schema file
  (`nextflow_schema.json`; nf-schema's Draft 2020-12 or nf-validation's
  Draft 7) to an IO schema: groups of parameters kept as `$defs`, path
  formats as file references (`mimetype` as `mediaType`, `format: path` a
  file unless `--directory` names it), sample-sheet schemas (`schema`, read
  from the pipeline directory) as tabular hints, `help_text` as Markdown
  descriptions, `hidden` and `errorMessage` as `x-ga4gh-hidden` and
  `x-ga4gh-error-message`; engine-local and display keywords (`exists`,
  `fa_icon`, `meta`, `uniqueEntries`) dropped, with notes; file outputs
  found by glob (`--out-file`, `--out-files`, `--out-dir`), and the engine
  binding (`descriptor_type` `NFL`). It replaces the separate
  `ga4gh-io-schema-converter` command of the draft in
  [#2](https://github.com/elixir-cloud-aai/ga4gh-io-schema/pull/2), which was never
  released. (#1)
- `ga4gh-io-schema convert snakemake`: converts a Snakemake config schema
  (YAML or JSON, Draft 4 to 2020-12) and sample-sheet schemas to an IO
  schema, with file references from documented, overridable heuristics, the
  sample sheets as tabular hints, file outputs found by glob
  (`--out-file`, `--out-files`, `--out-dir`), the engine binding
  (`descriptor_type` `SMK`), and notes on every decision to check; YAML
  needs the new `snakemake` extra. (#20)
- `ga4gh-io-schema convert wdl` converts the inputs and outputs of a WDL
  1.0, 1.1 or 1.2 workflow or task to an IO schema: WDL types (files as file
  references), literal defaults, common `parameter_meta` keys, nested
  inputs of calls, outputs (as the outputs model requires: required unless
  optional, no `null` outputs or list items), and the engine binding
  (`x-ga4gh-workflow` with the entry point and checksum,
  `x-ga4gh-parameter` with the WDL type); it needs the new `wdl` extra
  (miniwdl). (#22)
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
  descriptor, identified by `$schema`; it is the fallback for TRS servers
  without the file type `IO_SCHEMA` that is proposed now (see below). (#12)
- Shared conventions of all subcommands: input from a path or `-` (standard
  input), `--output` for the result, `--json` for results and errors as JSON
  objects. (#9)
- A CLI reference in the documentation, generated from the parser. (#9)
- A CWL converter, `ga4gh-io-schema convert cwl`: the inputs and outputs of
  CWL v1.0 to v1.2 documents (also packed) become an IO schema, with file
  references for files and directories, `format` as ontology term and
  required secondary files, `x-ga4gh-workflow` (descriptor type and
  version, checksum, entry point) and the CWL type of each parameter in
  `x-ga4gh-parameter`; what it can't convert (e.g., expressions) is
  reported as warnings. It reads only local files under the directory of
  the document (`--root` names another one) and rejects documents that
  would expand to very large schemas. It needs the optional dependency
  `cwl-utils` (`ga4gh-io-schema[cwl]`). (#21)
- The converters share their notes, errors, results and JSON paths, in
  `ga4gh_io_schema.converters.common`; the notes of the CWL converter
  (`ConversionNote`) are notes of this module too. (#54)
- `ConversionNote` still takes the location first, but its `repr` and
  dataclass fields list the message first, as those of all notes. (#54)
- All converters render the keys of JSON paths exactly as the validator
  does. Before, the WDL converter didn't bracket keys that start with `_`
  (which WDL names can't), and the CWL converter bracketed keys that end in
  a line break. (#54)
- Conformance: BCP 14 (RFC 2119, RFC 8174) key words, used consistently in
  the normative text; conformance classes (Schema document, Validator,
  Producer, Form renderer, Request builder, Output normaliser, WES server)
  with their requirements; a table of implementations. (#14)
- A language-neutral conformance suite in `tests/conformance/` (the
  positive and negative schema documents of the tests, moved from
  `tests/data/`), with a runner for this package. (#14)
- Markdown descriptions (`"x-ga4gh-description-format": "markdown"`) are
  CommonMark 0.31.2, with raw HTML shown as text, images shown as their alt
  text and not loaded, and links only with allowed schemes; of the GitHub
  Flavored Markdown extensions, only tables, strikethrough and autolinks are
  allowed. (#41)
- Versioning policy and governance note, and this changelog in the
  documentation, with the history of versions 0.1 and 0.2. (#14)
- A JavaScript runner of the conformance suite and the examples
  (`tests/js/`, run in CI) with Ajv and @hyperjump/json-schema, and a page
  "JavaScript validators" on how to set them up. The meta-schema applies
  the rules of `$defs/node` to nested schemas through explicit `$ref`s
  (`$defs/node/$defs/subschemas`), not `$dynamicAnchor`, which Ajv supports
  only at the root of a schema and would skip without an error. (#36)
- The meta-schema declares its vocabularies (`$vocabulary`: the Draft
  2020-12 vocabularies as required, the profile's vocabulary as optional),
  so that it is a dialect of Draft 2020-12. The specification states how
  input values and outputs are validated (against `properties.inputs` or
  `properties.outputs`, with the semantics of Draft 2020-12; `x-ga4gh-*`
  keywords don't change the result; request builders should assert
  `format`). Clients that validate values with the Draft 2020-12 dialect
  must check the IO schema against the profile first; Ajv and
  @hyperjump/json-schema need the setup in the JavaScript guide. The
  JavaScript tests validate values against the examples with both. (#37)
- Rules for `x-ga4gh-hidden` and `x-ga4gh-error-message`: form renderers
  show hidden inputs that users must set (required, no default) and hidden
  inputs whose values fail; an error message covers the failures at the
  location of the value that its schema describes, not those of nested
  values, replaces the validator's message, and the outermost message wins
  where several apply. (#40)
- Engine bindings: how input values become the `workflow_params` of a WES
  run request for `NFL`, `SMK`, `WDL` and `CWL` (names from
  `x-ga4gh-parameter`, WDL names qualified with the entry point, CWL `File`
  and `Directory` objects, no defaults inserted), which `RunRequest` fields
  come from TRS, and how servers translate `workflow_params` back; requirements
  for request builders and WES servers on the conformance page; a guide for
  WES clients and servers. (#18)
- The subcommand `ga4gh-io-schema wes-params` and the module
  `ga4gh_io_schema.wes`: validate input values against `inputs`, check file
  reference values against the rules and the deployment's allow-list, and
  write `workflow_params` or, with `--request`, a WES `RunRequest`. (#18)
- Language-neutral test vectors in `tests/vectors/` for the translation
  (`wes-params/`) and for file reference values (`file-values/`). (#18)
- The subcommand `ga4gh-io-schema outputs` and the module
  `ga4gh_io_schema.outputs`: build the normalised outputs object of a WES
  run from `RunLog.outputs` (outputs by name, also qualified WDL names and
  CWL `File` objects; Sapporo and WESkit listings matched by glob), validate
  it, and report ambiguous, unconverted and undeclared outputs, unmatched
  files and skipped entries of listings. Language-neutral test vectors in
  `tests/vectors/wes-outputs/`; a page "Output normaliser" with the
  supported shapes and their limits. The URIs of listed files percent-encode
  every character but the unreserved ones of RFC 3986. (#19) The vectors of
  Sapporo, WESkit, Toil and Cromwell are captured from real runs of these
  servers. (#55)
- The subcommand `ga4gh-io-schema wes-validate` and the function
  `from_workflow_params()` of `ga4gh_io_schema.wes`, the server side of the
  engine bindings: translate the `workflow_params` of a WES run request back
  into input values (keys matched with inputs, CWL `File` and `Directory`
  objects at file references turned into their `location`), validate them
  and check every file value, with errors located by a JSON Pointer into
  `workflow_params`, messages that don't repeat the value, and the body of
  the WES `ErrorResponse` (`error_response()`). Language-neutral test
  vectors in `tests/vectors/wes-requests/`; the valid vectors of
  `wes-params/` are checked to translate back to their values. In both
  directions, `unevaluatedProperties` and `unevaluatedItems` now apply per
  subschema, as in JSON Schema: before, a file reference in them was skipped
  when a sibling subschema (e.g., another branch of `allOf`) evaluated the
  member. The rules for servers in "From `workflow_params` back to input
  values" now decide what they left open: a member whose name is that of
  an input bound to another key is rejected; of several inputs that can
  bind to a key, the one whose first binding it is matches, and otherwise
  the request is rejected; CWL `File` and `Directory` objects with fields
  other than `class` and `location` (or `path`) are rejected, as are
  those of the wrong `class`. "File references" now says, like the engine
  bindings, that a branch of `anyOf` or `oneOf` that a value isn't valid
  against doesn't make it a file value. (#67)
- The TRS file type `IO_SCHEMA` is proposed for IO schemas, no longer
  deferred: clients look for the one file of that type first, and fall back
  to the file `ga4gh-io.schema.json` of type `OTHER` next to the primary
  descriptor, for TRS servers without it. "Discovery by clients" says how
  to match file entries: by `file_type` and normalised `path` only (empty
  and `.` segments removed), ignoring other fields such as `checksum`, with
  test vectors in `tests/vectors/trs-files/`. The module
  `ga4gh_io_schema.trs` implements the matching (`find_schema_file`) and
  finds the path of the primary descriptor for the `workflow_url`
  (`find_primary_descriptor_path`), normalised: "Workflow URLs in TRS" now
  says to use `main.wdl` for a listed `./main.wdl`. The
  host of the prototype uses it, the demo's `register.py` registers the
  schema as `IO_SCHEMA` with `--schema-file-type IO_SCHEMA`, and
  `trs_client.py` and a new page show discovery with TRS-Filer end to end.
  (#82)
- Engine bindings, "Workflow URLs in TRS": the recommended `workflow_url`
  is the plain primary descriptor by its path,
  `.../PLAIN_{type}/descriptor/{path}`, so that relative imports of
  multi-file workflows (e.g., a WDL import) resolve (RFC 3986) to files
  that TRS serves; the bare `.../PLAIN_{type}/descriptor` is for
  single-file workflows. `trs_descriptor_url` takes the path, and
  `wes-params --trs-url`, the form host and the TRS stub use it (from
  `primary_descriptor_path`, or from the TRS file list). New test vectors
  in `tests/vectors/workflow-urls/`, with imports. (#83)
- WES guide, "Can the WES fetch the workflow?": what a client must know
  about a WES before it sends a TRS URL as `workflow_url` (TRS URL
  support, reachable hosts), how deployments tell it today (client
  configuration, service registry, `service-info` tags), and the fallback
  with `workflow_attachment`; an open question in the roadmap for a WES
  `service-info` field. (#84)
- Prototype evaluation: each gap links to its issue (#82 to #85) and, for
  the fixed ones, to the pull request that closed it. (#74)
- A page "Transfer to GA4GH" with proposals for the transfer of the
  repository: naming (`ga4gh/io-schema`), the licence checked against the
  GA4GH Copyright Policy and GA4GH repositories, consistent copyright
  notices, a governance note (work stream, leads, approval path, status of
  the two-implementations requirement) and an identifier plan with
  `$id`s under `https://w3id.org/ga4gh/schema/io-schema/`. (#26)

### Fixed

- The transfer page names the `main` URL of the schemas, as the `$id`s of
  0.3 do, instead of a `v0.3.0` tag that doesn't exist; the check of
  schema URLs leaves out `$`-placeholders of rewrite rules. (#96)
- Validation against the meta-schema takes time roughly linear in the size
  of the schema, no longer exponential in its depth of nesting: deeply
  nested parameters (e.g., arrays of arrays, nested records) validate in
  milliseconds instead of seconds or minutes. The meta-schema accepts and
  rejects the same schemas as before (for schemas with several errors, the
  error that `ga4gh-io-schema validate` reports can differ). The
  conformance suite has a new positive case with deeply nested parameters,
  `nested.schema.json`. (#47)
- `validate_schema()` sets up the validation against a meta-schema once and
  reuses it: loading the profile, finding the local schemas, checking the
  meta-schema against its dialect and building the validator no longer
  happen on every call. Validating a small schema takes about 13 ms after
  the first call instead of 32 ms. A meta-schema, or a `schema_dir`, that
  changes between calls still gets a new validator. (#66)
- The meta-schema no longer requires `$schema` (it still checks its value),
  so that @hyperjump/json-schema, which removes `$schema` from a schema
  before it checks the schema against its dialect, accepts IO schemas with
  the profile as their dialect. IO schemas still must name the meta-schema
  in `$schema`, and validators reject documents without it: the Python
  validator as before, and the JavaScript setups of the documentation with a
  check of `$schema` before the meta-schema. Clients and meta-schemas that
  apply only the profile's meta-schema must now check `$schema` themselves.
  Clients that use hyperjump no longer need a copy of the IO schema that
  names Draft 2020-12 to validate values, unless an embedded resource of
  the IO schema names the profile. (#61)
- Values are matched against `pattern`, `patternProperties` and the names
  that `additionalProperties` and `unevaluatedProperties` check with
  ECMA-262 semantics in Unicode mode (regress, a new dependency), as
  JavaScript clients match them, in `wes-params`, `wes-validate`, `outputs`
  and the form proof of concept: `$` no longer matches before a trailing
  newline (`^[a-z]+$` rejected `"abc\n"` in clients but not on servers),
  and patterns such as `\p{L}`, which Python's `re` can't parse, work
  instead of failing with an unexpected error. `\w` and `\d` match ASCII
  only, as in ECMA-262. A new test vector, `NFL/pattern-trailing-newline`,
  covers the newline. (#77)
- `validate` checks the `regex` format of `pattern` and of the names in
  `patternProperties` as ECMA-262 in Unicode mode, so a schema with an
  invalid pattern (e.g., `(`, or `\-` outside a character class, which
  Python accepted) no longer passes and then fails on the first request
  that sets the input. Before, the format wasn't checked. (#77)
- `convert cwl` leaves out default files and directories with a forbidden
  scheme (e.g., `javascript:`), with a note, instead of copying them into
  the IO schema. (#77)
- The messages for missing extras name the extra and how to install it
  from a clone, instead of a package on PyPI, which doesn't exist. (#77)
- The wheel declares its licence (`Apache-2.0`) and ships the licence
  texts. (#77)
- Translating `workflow_params` back into input values
  (`from_workflow_params()`, `ga4gh-io-schema wes-validate`), and input
  values into `workflow_params`, takes time roughly linear in the size of
  the values, no longer in their size times their depth: the branches of
  `anyOf` and `oneOf` that apply at each level are no longer found by
  validating the whole subtree again. A recursive input (a string or a list
  of such inputs) with 10,000 strings translates there and back in under
  1 s at depth 40, instead of 37 s. Errors and results are unchanged.
  Schemas with `$dynamicRef`, `$dynamicAnchor`, an `$id` below the root or
  references outside the document translate as before, as their results
  can depend on the path to a subschema. The validation takes a little more
  of the stack: values are rejected as too deeply nested at a somewhat
  lower depth than before (about two thirds of it). (#86)
- Links in the documentation, the changelog and the tests, and the default
  repository of `examples/demo/register.py`, name the repository's new home
  `elixir-cloud-aai/ga4gh-io-schema` instead of `uniqueg/ga4gh-io-schema`;
  the "Edit" links of the docs open the `dev` branch. A test keeps the old
  name out of the repository, except where the move is explained. (#102)

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
