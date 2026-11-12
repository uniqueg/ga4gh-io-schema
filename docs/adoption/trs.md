# TRS

## Tool Registry Service (TRS) integration

IO schemas are published in a Tool Registry Service (TRS) next to the
workflow they describe, with the TRS API as it is: no change of the TRS
specification is needed. The schema's [`x-ga4gh-workflow`
block](../specification/identity.md#the-workflow-block) names the TRS tool
version and the checksum of the primary descriptor, so clients can check
that the schema belongs to the version they fetched it for.

### Publishing convention

For each descriptor type of a tool version (see [One workflow, several
engines](../specification/identity.md#one-workflow-several-engines)), the
IO schema is a file of the tool version with:

- **file type** `OTHER` (TRS `ToolFile.file_type`);
- **path** `ga4gh-io.schema.json`, in the directory of the primary
  descriptor (e.g., `workflows/ga4gh-io.schema.json` for the primary
  descriptor `workflows/variant_calling.wdl`);
- **content** an IO schema whose `$schema` names a version of the profile's
  meta-schema, and whose `x-ga4gh-workflow` names the tool version
  (`trs_tool_id`, `trs_version_id`), the descriptor type, the path and
  checksum of the primary descriptor and, for WDL, the entry point.

A file of type `OTHER` can be anything, so the path alone doesn't make a file
an IO schema: clients identify it by its `$schema`. A file at that path whose
`$schema` names no version of the profile is not an IO schema of this
profile, and clients ignore it. A client MUST NOT use a schema whose
`x-ga4gh-workflow.descriptor_type` differs from the descriptor type it was
fetched for.

TRS lists and serves files per descriptor type, so each type of a tool
version has its own `ga4gh-io.schema.json`, even at the same path. Where a
registry takes the files of a tool version from a source repository (e.g.,
a Git repository), a directory can hold only one file of that name: put the
primary descriptor of each descriptor type, with its schema, in a directory
of its own (e.g., `wdl/main.wdl` and `wdl/ga4gh-io.schema.json`, `cwl/main.cwl`
and `cwl/ga4gh-io.schema.json`).

### Discovery by clients

1. List the files of the tool version for the descriptor type:
   `GET /tools/{id}/versions/{version_id}/{type}/files`.
2. Find the entry of type `OTHER` with the path `ga4gh-io.schema.json` in the
   directory of the `PRIMARY_DESCRIPTOR`.
3. Fetch it: `GET /tools/{id}/versions/{version_id}/{type}/descriptor/{relative_path}`
   returns a `FileWrapper`; the schema is its `content` (or the file at its
   `url`).
4. Validate the schema against the meta-schema of the profile version that
   the client supports, from a local copy (see [Sources of
   schemas](../security.md#sources-of-schemas)).
5. Check `x-ga4gh-workflow` against the tool version (ids, descriptor type)
   and, where possible, the checksum against the primary descriptor (see
   [Drift](../specification/identity.md#drift)).

Without a schema, a client falls back to what it would do without the
profile (e.g., a plain JSON editor for the parameters).

### Deferred: an `IO_SCHEMA` file type

A dedicated TRS file type (e.g., `IO_SCHEMA`), accompanied by a field on TRS
file entries that names the schema standard (e.g., `ga4gh-io-schema`,
`nf-schema`), would let clients find schemas without a naming convention and
without excluding other schema standards. Both need a change of the TRS
specification; they are deferred to a later proposal to TRS, once the
convention above has been used in practice.

## Guide for TRS implementers

A TRS implementation needs no new endpoint or field to serve IO schemas: it
stores and serves the schema like any other file of type `OTHER`. To help
clients:

- Accept files of type `OTHER` at the path `ga4gh-io.schema.json` for every
  descriptor type, and serve them under the descriptor type they were
  registered for.
- Return `checksum` in the `FileWrapper` of the primary descriptor, so that
  clients can check for [drift](../specification/identity.md#drift) without
  downloading the descriptor.
- Optionally, when a schema is registered, validate it against the profile's
  meta-schema and check that its `x-ga4gh-workflow` names the tool version and
  matches the checksum of the primary descriptor; reject or flag schemas that
  don't.
