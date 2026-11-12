# Conformance

This page defines what it means to conform to the GA4GH IO Schema Profile:
the conformance classes, the requirements of each, the conformance suite that
tests them, and the known implementations.

## Notational conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT",
"SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and
"OPTIONAL" in this document are to be interpreted as described in BCP 14
([RFC 2119](https://www.rfc-editor.org/rfc/rfc2119),
[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)) when, and only when,
they appear in all capitals, as shown here.

The normative parts of the profile are the pages of the
[Specification](index.md) (except [Examples](examples.md)),
[Security considerations](../security.md), and the requirements in capitals
of the [WES](../adoption/wes.md) guide. Everything else (motivation,
rationale, related work, the other adoption guides, examples, notes and the
documentation of the tools) is informative. Where an informative page
repeats a requirement, the normative page that it links to governs.

## Conformance claims

A conformance claim names the conformance classes that a document or an
implementation meets, and the version of the profile, e.g., "Validator and
Form renderer of the GA4GH IO Schema Profile v0.3.0". An implementation
conforms to a class if it meets every MUST and MUST NOT requirement of that
class; it SHOULD meet the SHOULD requirements, and documents the ones it
doesn't meet and why.

## Conformance classes

| Class | What it is | Requirements |
| ----- | ----- | ----- |
| Schema document | An IO schema: a JSON document that describes the inputs and outputs of one workflow | [Schema document](#schema-document) |
| Validator | Software that decides whether a document is a conforming schema document | [Validator](#validator) |
| Producer | Software that generates schema documents, e.g., a converter from another description of parameters | [Producer](#producer) |
| Form renderer | A client that renders input forms from schema documents | [Form renderer](#form-renderer) |
| Request builder | A client that builds and submits run requests from input values | [Request builder](#request-builder) |
| Output normaliser | A client that matches the outputs of a run with the outputs of a schema document and shows them | [Output normaliser](#output-normaliser) |
| WES server | A WES implementation or gateway that validates run requests against schema documents (optional) | [WES server](#wes-server) |

One implementation can claim several classes; a portal, for example, is
typically a Form renderer, a Request builder and an Output normaliser. The
roles of [Security considerations](../security.md) map to the classes: its
**clients** are Form renderers, Request builders and Output normalisers, its
**servers** are WES servers, and its **execution side** is a WES server
together with the workflow engine that it runs.

### Schema document

1. A schema document MUST be a JSON object that is valid against the
   [meta-schema](meta-schema.md) of the version of the profile that it
   targets, and MUST name that meta-schema in `$schema`, by its versioned
   `$id`. Valid means valid with the `format` keywords of the meta-schema
   treated as assertions (e.g., `uri` for `x-ga4gh-ontology`, `regex` for
   `pattern`); JSON Schema 2020-12 treats `format` as an annotation by
   default.
2. A schema document MUST use the `x-ga4gh-*` keywords only as defined in
   [Keywords](keywords.md) and the [meta-schema](meta-schema.md), and MUST
   meet the requirements of [Keywords](keywords.md) for native JSON Schema
   keywords. Not all of them can be checked by the meta-schema (e.g., the
   use of `uniqueItems` instead of a custom keyword).
3. A schema document MUST meet the requirements for schemas of
   [Security considerations](../security.md): it is bundled (see
   [Sources of schemas](../security.md#sources-of-schemas)), it defines no
   inputs for secrets (see [Secrets](../security.md#secrets)), and it marks
   every file input and output as a [file reference](files.md) (see
   [URIs and file references](../security.md#uris-and-file-references)).
   Its regular expressions SHOULD follow
   [Regular expressions and size limits](../security.md#regular-expressions-and-size-limits).
4. A schema document MUST meet the requirements of
   [File references](files.md) for every file reference.
5. A schema document MUST meet the requirements of
   [Identity and engine binding](identity.md) for its `$id`
   ([Identifiers and versions](identity.md#identifiers-and-versions)), its
   `x-ga4gh-workflow` ([The workflow block](identity.md#the-workflow-block))
   and its `x-ga4gh-parameter` bindings
   ([Parameter bindings](identity.md#parameter-bindings)). A schema
   document published in a TRS SHOULD carry `trs_tool_id`,
   `trs_version_id`, `primary_descriptor_path` and at least one
   `checksum`.
6. A schema document MUST meet the requirements of [Outputs](outputs.md)
   for its `outputs` ([The outputs schema](outputs.md#the-outputs-schema))
   and for every `x-ga4gh-output-glob`. It SHOULD have `outputs` where the
   workflow language declares outputs, and SHOULD NOT allow `null` in
   outputs.

### Validator

1. A validator supports one or more versions of the profile, and names
   them in its conformance claim. For each of them, it MUST accept every
   document that meets requirement 1 of [Schema document](#schema-document)
   and MUST reject every other document that names that version.
   Together with requirement 3, this means that, when it validates against
   the profile (no other meta-schema asked for), it MUST accept every case
   in `valid/` and MUST reject every case in `invalid/` of the
   [conformance suite](#conformance-suite) of that version.
2. A validator MUST check the `format` keywords that the meta-schema uses
   (e.g., `uri` for `x-ga4gh-ontology`). As an exception to requirement 1,
   it MAY skip the `regex` format, which not every regular expression
   engine can check for the ECMA-262 dialect; a document that it accepts
   without that check is not thereby shown to conform.
3. Unless it was explicitly asked to use another meta-schema (e.g., a
   draft of a new version), a validator MUST reject a document without
   `$schema`, or whose `$schema` names no version of the profile that it
   supports. A document checked against another meta-schema is not
   thereby a conforming schema document.
4. A validator MUST load the meta-schema and its vocabularies from local
   copies and MUST NOT retrieve them, or any other reference, over the
   network (see [Sources of schemas](../security.md#sources-of-schemas)).
5. A validator SHOULD report the location of each error in the document,
   e.g., as a JSON Pointer.

Requirements 2 and 3 are what some negative cases of the suite expect: a
validator that doesn't check formats accepts `ontology-not-uri`, and one
that validates against whatever meta-schema `$schema` names (e.g.,
draft-07) accepts `foreign-schema` and `plain-json-schema`.

### Producer

1. Every schema document that a producer emits MUST conform to
   [Schema document](#schema-document), for the version of the profile that
   it names in `$schema`.
2. A producer SHOULD report the parts of its source that it can't express in
   the profile (e.g., as warnings) instead of dropping them silently.
3. A producer SHOULD map the file types of its source (e.g., CWL `File`,
   WDL `File`, nf-schema `format: file-path`) to file references as
   described in
   [Mapping to workflow languages](files.md#mapping-to-workflow-languages).
4. A producer SHOULD fill `x-ga4gh-workflow` from its source (the
   descriptor type, the entry point where the descriptor type needs one,
   and, where known, the TRS identifiers and the checksum of the primary
   descriptor), and SHOULD add `x-ga4gh-parameter` where the name or type
   of an engine parameter isn't clear from the property (see
   [Identity and engine binding](identity.md)).
5. A producer MUST convert the outputs that its source declares (see
   [The outputs schema](outputs.md#the-outputs-schema)), and SHOULD follow
   [Notes on engines and servers](outputs.md#notes-on-engines-and-servers)
   (e.g., `x-ga4gh-output-glob` for outputs that the engine doesn't report
   by name, never copied from CWL `outputBinding.glob`).

### Form renderer

1. A form renderer SHOULD check that a schema document conforms (as a
   [Validator](#validator) does) before it renders a form from it, and MUST
   NOT render forms from schema documents with references that it can't
   resolve locally.
2. A form renderer MUST let users set every input of `inputs`; it MAY show
   inputs with `"x-ga4gh-hidden": true` only on request (e.g., under
   "Advanced"), except that it MUST show hidden inputs that users must set
   and hidden inputs whose values fail validation, as defined in
   [Hidden inputs](keywords.md#hidden-inputs).
3. A form renderer MUST meet the rules of [UI widgets](widgets.md#rules):
   (a) it MUST render an input whose `x-ga4gh-ui-widget` it doesn't know, or
   whose widget doesn't fit the input's schema (e.g., an output viewer), as
   it renders inputs of the same type without a widget hint; (b) for the
   widgets of the vocabulary that it renders, it MUST produce values as
   defined in [Input widgets](widgets.md#input-widgets).
4. A form renderer MUST meet the rules of
   [Rendering schemas and outputs](../security.md#rendering-schemas-and-outputs)
   for the text of a schema document, and MUST render Markdown descriptions
   as defined in [Markdown descriptions](keywords.md#markdown-descriptions)
   (or show them as plain text). When a value fails validation, it
   SHOULD show the `x-ga4gh-error-message` that covers the failure, where
   there is one, in place of the validator's message, as defined in
   [Error messages](keywords.md#error-messages).
5. A form renderer SHOULD NOT download data files into a browser to
   validate them (see
   [Validation of data files on the server](../security.md#validation-of-data-files-on-the-server)).
6. A form renderer MUST meet the rules of [Drift](identity.md#drift) and
   of [The workflow block](identity.md#the-workflow-block) for a schema
   document fetched for a tool version: it MUST NOT use a schema document
   silently whose checksum or TRS identifiers don't match the workflow.

### Request builder

1. A request builder MUST validate the input values against `inputs` of the
   schema document before it submits a run request, and MUST NOT submit
   values that fail.
2. A request builder MUST check the scheme of every file reference against
   the allow-list of the deployment before it submits it (see
   [URIs and file references](../security.md#uris-and-file-references)).
3. A request builder MUST meet the rules of
   [Access to data](../security.md#access-to-data) for clients: it SHOULD
   submit DRS objects as `drs://` identifiers, and MUST NOT put signed URLs,
   access tokens or other credentials in `workflow_params`.
4. A request builder MUST meet the rules of [Drift](identity.md#drift),
   as for form renderers, before it submits a run request.
5. A request builder MUST translate the input values into the
   `workflow_params` of the schema document's descriptor type as defined in
   [Engine bindings](engine-bindings.md): names from `x-ga4gh-parameter`
   (qualified with the entry point for WDL), file values as the engine
   takes them (CWL `File` and `Directory` objects), no `default`s inserted,
   and colliding names rejected. It MUST reject schema documents whose
   descriptor type has no binding (`GALAXY` in version 0.3).
6. A request builder MUST set `workflow_type` and `workflow_type_version`
   of the WES `RunRequest` from `x-ga4gh-workflow` (the version from TRS
   only where the schema document has none), and `workflow_url` to a URL of
   the workflow that the deployment accepts, with the CWL entry point as
   its fragment (see [Run requests](engine-bindings.md#run-requests)).
7. A request builder MUST produce the results of the
   [test vectors](engine-bindings.md#test-vectors): the `workflow_params`
   of every `wes-params` case, and the decision of every `file-values`
   case.

### Output normaliser

1. An output normaliser MUST build the
   [normalised outputs object](outputs.md#the-normalised-outputs-object) of
   a run, keyed by the outputs of the schema document, with values in the
   shapes of [Values](outputs.md#values): absent, never `null`, for outputs
   that the run didn't produce, and without outputs that the schema
   document doesn't declare.
2. An output normaliser MUST check the scheme of every output reference
   against the allow-list of the deployment before it shows the output as a
   link or loads it into a viewer, and MUST meet the rules of
   [Rendering schemas and outputs](../security.md#rendering-schemas-and-outputs)
   for the outputs it shows.
3. An output normaliser MUST find each output by name first and otherwise
   by its `x-ga4gh-output-glob`, as defined in
   [Finding outputs](outputs.md#finding-outputs), and MUST check the files
   that the server lists before it matches globs against them.
4. An output normaliser MUST validate the normalised outputs object of a
   run that completed against `outputs`, and report a run whose object
   isn't valid as non-conformant; it MUST NOT drop or change outputs to
   make the object valid. It MUST report ambiguous matches (e.g., several
   files for a one-file output), skipped listed files, and the outputs that
   the engine reports but the schema document doesn't declare, instead of
   dropping them silently. Optional outputs that it doesn't find are
   absent, not errors.
5. An output normaliser MUST show the outputs of a run that didn't
   complete as partial, as defined in
   [Runs that don't complete](outputs.md#runs-that-dont-complete), and the
   outputs of a non-conformant run with the same warning, keeping all of
   them.

### WES server

Validation of run requests against schema documents is OPTIONAL for a WES
implementation: a WES server that doesn't validate still conforms to WES,
and this class applies only to servers that claim it. The
[WES](../adoption/wes.md) guide recommends validation where a schema
document from a trusted source is available.

1. A WES server MUST use only schema documents from trusted sources and
   MUST NOT accept schema documents supplied by clients (see
   [Sources of schemas](../security.md#sources-of-schemas)).
2. A WES server MUST validate with a validator that meets
   [Validator](#validator), and MUST reject (fail closed) requests for a
   workflow whose schema document has references that it can't resolve
   locally.
3. A WES server MUST reject a request that fails validation with
   `HTTP 400 Bad Request` and the WES `ErrorResponse`, whose `msg` names the
   location of the error as a JSON Pointer relative to `workflow_params`
   and the rule that failed, or the `x-ga4gh-error-message` that covers the
   failure (see [Error messages](keywords.md#error-messages),
   [WES](../adoption/wes.md) and
   [Error messages and logs](../security.md#error-messages-and-logs)).
4. A WES server MUST meet all requirements for servers of
   [Security considerations](../security.md) (sources of schemas, regular
   expressions and size limits, URI schemes, error messages and logs,
   validation of data files), and its execution side the requirements for
   staging data (hosts of file references,
   [Access to data](../security.md#access-to-data)).
5. A WES server MUST meet the rules of [Drift](identity.md#drift): if the
   checksum of the primary descriptor doesn't match the schema document,
   it rejects the schema document or logs a warning before it uses it.
6. A WES server MUST translate `workflow_params` back into input values with
   the engine binding of the request's `workflow_type` before it validates
   them, and MUST report errors at their location in `workflow_params`, as
   defined in [From `workflow_params` back to input
   values](engine-bindings.md#from-workflow_params-back-to-input-values).

## Conformance suite

The conformance suite is a set of language-neutral test cases in
[`tests/conformance/`](https://github.com/uniqueg/ga4gh-io-schema/tree/main/tests/conformance)
of the repository: JSON files, without code, that any implementation can run
with a runner of its own.

```text
tests/conformance/
└── schema-documents/
    ├── valid/      # *.schema.json: conforming schema documents
    └── invalid/    # *.schema.json: non-conforming schema documents
```

- **Schema documents** test the class [Validator](#validator): a validator
  MUST accept every `*.schema.json` file in `valid/` and MUST reject every
  one in `invalid/`. Each negative case breaks the rule that its file name
  names (a few, such as `empty`, also break others). The valid cases, and
  the negative cases other than those about `$schema` (`empty`,
  `foreign-schema`, `missing-schema`, `plain-json-schema`), name the
  meta-schema by its versioned `$id`; no case has other references, so a
  runner needs only the
  meta-schema and vocabularies of
  [`schemas/`](https://github.com/uniqueg/ga4gh-io-schema/tree/main/schemas),
  loaded from local copies: a runner maps each `$id` of `schemas/` to its
  file. Error messages differ between validators and are not part of the
  suite. Files ending in `.license` hold licence information
  ([REUSE](https://reuse.software/)) and are not cases.
- **Test vectors** in
  [`tests/vectors/`](https://github.com/uniqueg/ga4gh-io-schema/tree/main/tests/vectors)
  test the class [Request builder](#request-builder): the translation of
  input values into `workflow_params` for each descriptor type
  (`wes-params/`), and the checks of file reference values (schemes,
  compact DRS identifiers, paths; `file-values/`). Their format is described
  in [Engine bindings](engine-bindings.md#test-vectors); this package runs
  them with `tests/test_wes.py`.
- Cases for the other classes (e.g., for the normalisation of outputs) are
  added to the suite with the features they test.

The runner of this package is `tests/test_conformance.py`; it checks every
case against the [Python API](../tools/validator.md#python-api) of the
validator:

```bash
pytest tests/test_conformance.py --no-cov
```

(`--no-cov` turns off the coverage check of the whole test suite, which a
run of one file doesn't meet.)

The tests of the [command-line interface](../tools/cli.md) run the same cases
through `ga4gh-io-schema validate` and also check the message of each
negative case (see [Development](../development.md#unit-tests-pytest)). A
new rule of the meta-schema comes with a negative case in the suite, and a
change of a rule that makes a valid case fail is a breaking change (see
[Versioning and governance](../governance.md)).

## Implementations

GA4GH approval of a standard requires at least two independent
implementations that interoperate. Known implementations, and the classes
that they implement or plan to implement:

| Implementation | Language | Classes | Status |
| ----- | ----- | ----- | ----- |
| [`ga4gh-io-schema`](../tools/index.md) (this repository) | Python | Validator | Available (`ga4gh-io-schema validate`); passes the conformance suite |
| [`ga4gh-io-schema`](../tools/index.md) (this repository) | Python | Request builder (translation and checks; submission is left to the caller) | Available (`ga4gh-io-schema wes-params`); passes the test vectors |
| [`ga4gh-io-schema`](../tools/index.md) (this repository) | Python | Producer, Output normaliser | Planned (converters, normalisation of outputs) |
| [ELIXIR Cloud Components](https://github.com/elixir-cloud-aai/cloud-components) | TypeScript | Form renderer, Request builder, Output normaliser | Planned |

Further implementations are welcome: propose an entry for this table with a
pull request (see [Versioning and governance](../governance.md#proposing-changes)).
