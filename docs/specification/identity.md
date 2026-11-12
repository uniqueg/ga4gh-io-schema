# Identity and engine binding

An IO schema describes one version of one workflow or tool, written for one
workflow language. This page defines how a schema says which version and
language that is, how clients detect a schema that no longer matches the
workflow (drift), and what a translator needs to turn input values into the
parameters of the engine. How schemas are published in a Tool Registry
Service (TRS) is described in [TRS](../adoption/trs.md).

The key words MUST, MUST NOT, SHOULD and MAY are used as described in
[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119).

## Identifiers and versions

Two identifiers and their versions are involved:

- **The profile:** `$schema` names the meta-schema of the profile by its
  versioned `$id`, which contains the release tag of the profile (e.g.,
  `v0.3.0`, see [Referencing the
  meta-schema](meta-schema.md#referencing-the-meta-schema)). The `$id`s of
  the meta-schema and its vocabularies name the same tag; they never name a
  branch.
- **The IO schema itself:** `$id` identifies the schema.

Rules for the `$id` of an IO schema:

- It SHOULD be present. If it is, it MUST be an absolute URI (checked by the
  meta-schema; the check that it starts with a scheme works in every
  validator, the full `format: uri` check only in validators that assert
  formats, like the [validator](../tools/validator.md) of this package).
- It MUST be stable and versioned: the content behind an `$id` never changes;
  a changed schema gets a new `$id`. For a schema in a TRS, the `$id` SHOULD
  contain the TRS version id of the workflow (e.g.,
  `https://example.org/schemas/variant-calling/wdl/1.2.0`).
- It MUST NOT be the URL of a branch, whose content moves. The meta-schema
  rejects the common forms at GitHub and GitLab (`refs/heads/`, or `main`,
  `master`, `dev`, `develop` or `HEAD` in place of a tag or commit); other
  branch URLs aren't detectable, and the check is case-sensitive, so it is a
  best-effort check: the rule applies to every branch URL.
- It MUST use a domain or namespace that the author controls (e.g., not
  `ga4gh.org` for a schema that GA4GH doesn't publish). The examples of this
  documentation use `example.org`.

The meta-schema checks only the form of the `$id` (absolute, not a known
branch URL); whether it is stable, versioned and in the author's namespace
is up to the author and, for published schemas, the registry.

The `$id` doesn't have to resolve: clients get schemas from TRS (or another
trusted source, see [Sources of schemas](../security.md#sources-of-schemas)),
not by fetching the `$id`.

## The workflow block

The top-level keyword `x-ga4gh-workflow` ties an IO schema to a workflow
version and its engine. It is allowed only at the top level of an IO schema;
the meta-schema rejects it in nested schemas.

```json
{
  "$schema": "https://raw.githubusercontent.com/uniqueg/ga4gh-io-schema/v0.3.0/schemas/ga4gh-io-profile.schema.json",
  "$id": "https://example.org/schemas/variant-calling/wdl/1.2.0",
  "x-ga4gh-workflow": {
    "trs_tool_id": "#workflow/example.org/variant-calling",
    "trs_version_id": "1.2.0",
    "descriptor_type": "WDL",
    "descriptor_type_version": "1.1",
    "primary_descriptor_path": "workflows/variant_calling.wdl",
    "checksum": [
      {
        "type": "sha-256",
        "checksum": "9c1e4a7f2b5d8e0a3c6f9b2e5d8a1c4f7b0e3a6d9c2f5b8e1a4d7c0f3b6e9a2d"
      }
    ],
    "entry_point": "variant_calling"
  },
  "type": "object",
  "properties": {
    "inputs": {}
  }
}
```

The full schema is [Example 3](examples.md#example-3-workflow-bound-to-an-engine).

| Field | Value | Meaning |
| ----- | ----- | ----- |
| `trs_tool_id` | string | The id of the tool in the TRS (`Tool.id`). |
| `trs_version_id` | string | The id of the tool version in the TRS (`ToolVersion.id`). |
| `descriptor_type` | `CWL`, `WDL`, `NFL`, `SMK` or `GALAXY` (required) | The TRS descriptor type, which is also the WES `workflow_type`. |
| `descriptor_type_version` | string | The version of the workflow language (e.g., `1.1` for WDL, `DSL2` for Nextflow, `v1.2` for CWL), one of the `descriptor_type_version` values of the TRS tool version; the WES `workflow_type_version`. |
| `primary_descriptor_path` | string | The path of the primary descriptor (TRS file type `PRIMARY_DESCRIPTOR`), relative to the root of the tool version's files. |
| `checksum` | array of `{"type": …, "checksum": …}` | Checksums of the primary descriptor, in the format of TRS checksums: `type` is the algorithm, as in TRS by its Hash Name String in the [GA4GH Checksum Hash Algorithm Registry](https://github.com/ga4gh-discovery/ga4gh-checksum/blob/master/hash-alg.csv) (e.g., `sha-256`), `checksum` the hex-encoded digest. |
| `entry_point` | string (required for `WDL`) | The entry point of the engine (see below). |

Field names follow TRS and WES, which use `snake_case`. Other fields are
rejected. `descriptor_type` takes the descriptor types of TRS 2.0.1; a new
type in TRS needs a new version of the profile. The meta-schema checks that
a checksum is hex-encoded, not that its length fits the algorithm; a
truncated checksum shows up as a mismatch (see [Drift](#drift)).

Only `descriptor_type` is required, so that a schema can be written (or
converted) before the workflow is registered in a TRS. A schema published in
a TRS SHOULD carry `trs_tool_id`, `trs_version_id`, `primary_descriptor_path`
and at least one `checksum`. A client that fetched the schema for a tool
version SHOULD check that `trs_tool_id` and `trs_version_id`, where present,
name that tool version, and MUST NOT use the schema silently if they don't
(see [Drift](#drift)).

### Entry points

The entry point says which part of the descriptor the inputs belong to:

| Descriptor type | `entry_point` | Effect on the engine parameters |
| ----- | ----- | ----- |
| `WDL` | The name of the workflow, or of the task for a document with a single task and no workflow. Required. | WDL input names are qualified with it: the input `sample` of the workflow `variant_calling` is `variant_calling.sample`. |
| `NFL` | The named workflow run with `-entry`; absent for the unnamed (main) workflow. | Doesn't change the names of the parameters. |
| `CWL` | The id of the process to run in a document with several processes (e.g., `#main` in a packed document with `$graph`); absent for a document with one process. | Selects the process whose inputs the schema describes; WES clients append it to the workflow URL as a fragment. |
| `SMK` | Not used. | |
| `GALAXY` | Not used. | |

## Parameter bindings

By default, each property of `inputs` (and of `outputs`) is a parameter of
the engine with the same name, and its JSON Schema type, together with the
[file reference](files.md) annotation, decides how the value is passed. Where that
isn't enough, the property carries `x-ga4gh-parameter`:

| Field | Value | Meaning |
| ----- | ----- | ----- |
| `name` | string | The name of the engine parameter, relative to the entry point, where it differs from the name of the property (e.g., `call_variants.threads` for the input `threads` of the WDL call `call_variants`, which a converter may expose as `caller_threads`). |
| `type` | string | The type of the parameter as declared in the workflow language (e.g., `Array[File]+` or `Pair[Int,String]` in WDL, `File[]?` in CWL). |

At least one field is required, and other fields are rejected.
`x-ga4gh-parameter` belongs on the schemas of the properties of `inputs` and
`outputs`. The meta-schema accepts it at any depth, like the other keywords
of every schema; elsewhere it has no meaning and clients ignore it.

The `name` is what a translator uses as the key of the value in the engine's
parameters, qualified as the descriptor type requires (e.g., with the WDL
entry point: `variant_calling.call_variants.threads`). The `type` is
informative: translators and converters use it where the JSON Schema type
leaves a choice (e.g., a WDL `Pair` and a struct with the members `left` and
`right` are both JSON objects), and to check that the schema still matches
the descriptor. The rules that turn input values into WES `workflow_params`
for each descriptor type, using these fields, are part of the engine
bindings ([#18](https://github.com/uniqueg/ga4gh-io-schema/issues/18)).

For example, the input `caller_threads` of [Example
3](examples.md#example-3-workflow-bound-to-an-engine) is the input `threads`
of the call `call_variants`:

```json
"caller_threads": {
  "type": "integer",
  "minimum": 1,
  "default": 4,
  "title": "Threads of the variant caller",
  "x-ga4gh-parameter": {
    "name": "call_variants.threads",
    "type": "Int"
  }
}
```

## Drift

A schema drifts when the workflow changes and the schema doesn't. The
checksum of the primary descriptor detects it:

- A consumer (client, WES server or converter) that has the primary
  descriptor, or its checksum from TRS (`FileWrapper.checksum`), and supports
  one of the algorithms of `checksum` SHOULD compare them. It computes the
  checksum over the bytes of the primary descriptor as TRS serves them
  (`FileWrapper.content` in UTF-8, or the file at `FileWrapper.url`), and
  compares algorithm names and hex digests case-insensitively.
- A consumer that finds a mismatch MUST NOT use the schema silently: it MUST
  either reject the schema, or warn that the schema may not match the
  workflow before it uses it: a client warns the user (e.g., next to the
  form), a server logs a warning.
- A consumer that can't compare (no checksum in the schema, no supported
  algorithm, or no access to the descriptor) treats the schema as
  unverified; it MAY use it.

The checksum covers the primary descriptor only. A change in an imported file
(e.g., a WDL `import` or a Nextflow module) is not detected; authors SHOULD
publish a new tool version, with a new schema, for every change of the
workflow.

## One workflow, several engines

TRS lists files per descriptor type, and the engine binding differs between
languages, so a workflow published for several engines has one IO schema per
descriptor type, each with its own `x-ga4gh-workflow` and `$id` (e.g.,
`…/variant-calling/wdl/1.2.0` and `…/variant-calling/cwl/1.2.0`). Content that
the schemas share, such as titles, descriptions and constraints of the
inputs, is written once and referenced with `$ref`. Because IO schemas MUST
be bundled (see [Sources of schemas](../security.md#sources-of-schemas)), the shared
definitions are bundled into each published schema, e.g., as embedded
resources in `$defs` with their own `$id`, as described in [JSON Schema
Core, §9.3](https://json-schema.org/draft/2020-12/json-schema-core#section-9.3).
