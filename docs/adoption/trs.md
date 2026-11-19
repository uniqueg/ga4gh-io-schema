# TRS

## Tool Registry Service (TRS) integration

IO schemas are published in a Tool Registry Service (TRS) next to the
workflow they describe. The profile proposes a TRS file type for them,
`IO_SCHEMA` (see [Proposed: the `IO_SCHEMA` file
type](#proposed-the-io_schema-file-type)); until TRS servers have it, they
publish IO schemas with the TRS API as it is, as files of type `OTHER` at a
fixed path. The schema's [`x-ga4gh-workflow`
block](../specification/identity.md#the-workflow-block) names the TRS tool
version and the checksum of the primary descriptor, so clients can check
that the schema belongs to the version they fetched it for.

### Publishing convention

For each descriptor type of a tool version (see [One workflow, several
engines](../specification/identity.md#one-workflow-several-engines)), the
IO schema is a file of the tool version with:

- **file type** `IO_SCHEMA` (TRS `ToolFile.file_type`), on TRS servers that
  have it, or else `OTHER`;
- **path** `ga4gh-io.schema.json`, in the directory of the primary
  descriptor (e.g., `workflows/ga4gh-io.schema.json` for the primary
  descriptor `workflows/variant_calling.wdl`); required for type `OTHER`,
  where the path is what clients look for, and recommended for type
  `IO_SCHEMA`, so that the same files work on servers with either type;
- **content** an IO schema whose `$schema` names a version of the profile's
  meta-schema, and whose `x-ga4gh-workflow` names the tool version
  (`trs_tool_id`, `trs_version_id`), the descriptor type, the path and
  checksum of the primary descriptor and, for WDL, the entry point.

A descriptor type of a tool version has at most one file of type
`IO_SCHEMA`. A file of type `OTHER` can be anything, so the path alone
doesn't make a file an IO schema: clients identify it by its `$schema`, as
they do for files of type `IO_SCHEMA`. A file whose `$schema` names no
version of the profile is not an IO schema of this profile, and clients
ignore it. A client MUST NOT use a schema whose
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
2. Find the IO schema among the entries, by the [matching
   rules](#matching-file-entries) below: the entry of type `IO_SCHEMA`, or,
   if there is none, the entry of type `OTHER` with the path
   `ga4gh-io.schema.json` in the directory of the `PRIMARY_DESCRIPTOR`.
3. Fetch it by its path as listed (percent-encoded):
   `GET /tools/{id}/versions/{version_id}/{type}/descriptor/{relative_path}`
   returns a `FileWrapper`; the schema is its `content` (or, if it has no
   `content`, the file at its `url`).
4. Validate the schema against the meta-schema of the profile version that
   the client supports, from a local copy (see [Sources of
   schemas](../security.md#sources-of-schemas)).
5. Check `x-ga4gh-workflow` against the tool version (ids, descriptor type)
   and, where possible, the checksum against the primary descriptor (see
   [Drift](../specification/identity.md#drift)).

Without a schema, a client falls back to what it would do without the
profile (e.g., a plain JSON editor for the parameters).

#### Matching file entries

All fields of a TRS `ToolFile` are optional, and servers list paths in
different forms (e.g., `ga4gh-io.schema.json`, `./ga4gh-io.schema.json` or
`/ga4gh-io.schema.json`). Clients compare entries by `file_type` and
normalised `path` only:

- **Other fields are ignored**, e.g., `checksum`, and fields that the client
  doesn't know. Comparing whole entries misses the schema as soon as an
  entry has another field.
- **Entries without** a `file_type` or a `path` (a string) **are ignored.**
- **Paths are normalised** by removing empty segments and `.` segments
  (`./wdl/main.wdl`, `/wdl/main.wdl` and `wdl//main.wdl` are all
  `wdl/main.wdl`), and compared case-sensitively. Entries whose path has a
  `..` segment are ignored.
- **The type `IO_SCHEMA` comes first:** if exactly one entry has it, that is
  the IO schema, whatever its path. If several have it, the tool version is
  ambiguous: the client doesn't guess, and takes none, not even an entry of
  type `OTHER`.
- **Then `OTHER` at the conventional path:** the directory of the primary
  descriptor is that of the normalised path of the entries of type
  `PRIMARY_DESCRIPTOR`; if there is none, or they are in different
  directories, there is no IO schema. Otherwise, the IO schema is the
  entry of type `OTHER` whose normalised path is `ga4gh-io.schema.json` in
  that directory; entries of other types at that path (e.g., `TEST_FILE`)
  don't count. If several entries of type `OTHER` have that normalised path
  (e.g., `ga4gh-io.schema.json` and `./ga4gh-io.schema.json`), the client
  takes none, as for several entries of type `IO_SCHEMA`.

The client fetches the schema by the path as the entry lists it, not by the
normalised one, as servers may store paths as they were registered.

The test vectors in
[`tests/vectors/trs-files/cases.json`](https://github.com/elixir-cloud-aai/ga4gh-io-schema/blob/main/tests/vectors/trs-files/cases.json)
are lists of file entries, such as answers with checksums or with `./` in
paths, each with the entry that a client finds (`schemaFile`: its `path` as
listed and its `file_type`), or `null` for none. The package implements the
rules as
[`ga4gh_io_schema.trs.find_schema_file`](../tools/trs.md).

### Proposed: the `IO_SCHEMA` file type

The profile proposes a TRS file type `IO_SCHEMA` for the IO schema of a
descriptor type of a tool version: at most one per descriptor type, at any
path (`ga4gh-io.schema.json` next to the primary descriptor is
recommended), listed by `{type}/files` and served by
`{type}/descriptor/{relative_path}` like files of type `OTHER`. With it,
clients find the schema by its type alone, and servers can check schemas
when they are registered without relying on a file name.

The convention with `OTHER` and a fixed path works with every TRS server,
but it proved brittle in practice: the first version of the
[prototype](prototype.md)'s host compared whole file entries and missed the
schema as soon as an entry carried a `checksum`, and a path such as
`./ga4gh-io.schema.json` doesn't equal `ga4gh-io.schema.json` without
normalisation (see the [prototype evaluation](prototype-evaluation.md)).
The [matching rules](#matching-file-entries) fix this for clients that
implement them; a file type of its own avoids the comparison of paths
altogether.

[TRS-Filer](https://github.com/elixir-cloud-aai/trs-filer), the TRS
implementation of ELIXIR On-Cloud, accepts `IO_SCHEMA` as an experimental
extension of the TRS file types (on its development branch, not yet in a
release); the [demo with TRS-Filer](demo-trs-filer.md) registers a schema
of that type with it and discovers it as a client. The type is to be
proposed to the TRS specification with this evidence. Until TRS adopts it:

- **TRS servers without `IO_SCHEMA`** reject or don't list files of that
  type: publish the schema there as `OTHER` at `ga4gh-io.schema.json`, the
  fallback.
- **Clients** look for `IO_SCHEMA` first and fall back to `OTHER` at the
  conventional path, as the [matching rules](#matching-file-entries) say.
  Clients that accept only the file types of TRS 2.0.2 may reject lists of
  files with `IO_SCHEMA`.

A field on TRS file entries that names the schema standard of a file (e.g.,
`ga4gh-io-schema`, `nf-schema`) is still deferred (see
[Roadmap](../roadmap.md#deferred)): `IO_SCHEMA` files are IO schemas of
this profile, identified by their `$schema`.

## Guide for TRS implementers

A TRS implementation needs no new endpoint to serve IO schemas. To help
clients:

- Support the file type `IO_SCHEMA` (see [Proposed: the `IO_SCHEMA` file
  type](#proposed-the-io_schema-file-type)): accept at most one file of that
  type per descriptor type of a tool version, list it in `{type}/files`,
  and serve it by its path, as files of type `OTHER`.
- Accept files of type `OTHER` at the path `ga4gh-io.schema.json` for every
  descriptor type, and serve them under the descriptor type they were
  registered for, for the fallback.
- List paths as they were registered, and serve files by those paths.
- Return `checksum` in the `FileWrapper` of the primary descriptor, so that
  clients can check for [drift](../specification/identity.md#drift) without
  downloading the descriptor.
- Optionally, when a schema is registered, validate it against the profile's
  meta-schema and check that its `x-ga4gh-workflow` names the tool version and
  matches the checksum of the primary descriptor; reject or flag schemas that
  don't.
