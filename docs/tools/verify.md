# Workflow block check

The `verify` subcommand of the [command-line interface](cli.md), and
`check_workflow()` of the `ga4gh_io_schema.workflow` module, check the
workflow block of an IO schema (`x-ga4gh-workflow`) against the workflow
version that the schema is used for: step 2 of the [guide for portals and
clients](../adoption/portals.md#2-check-the-workflow-block), by the rules of
[Drift](../specification/identity.md#drift). They compare:

- `trs_tool_id`, `trs_version_id` and `descriptor_type`, where the schema
  has them and the caller gives them, with the tool version and descriptor
  type that the schema was fetched for;
- each `checksum` of the schema with the checksums of the primary
  descriptor by the same algorithm: those from TRS (`FileWrapper.checksum`),
  and those computed over the descriptor (`FileWrapper.content` in UTF-8,
  or the bytes of a file) for `md5`, `sha-1`, `sha-256` and `sha-512`.
  Algorithm names and digests are compared case-insensitively.

The result is the list of mismatches and whether the schema is verified:

- **Mismatch:** a field differs. The client must not use the schema
  silently: it refuses it, or warns that it may not match the workflow.
- **Verified:** no mismatch, and at least one checksum was compared.
- **Unverified:** no mismatch, but no checksum could be compared (no
  checksum in the schema, no supported algorithm, or no descriptor). The
  client may use the schema, and may say that it is unverified.

The check doesn't validate the schema against the profile (step 3 of the
guide): an id of the wrong type, e.g., a number, mismatches the id that
is given, and checksums of the wrong type are skipped. The [form
host](../adoption/form.md) of the prototype refuses schemas from TRS with a
mismatch, and uses a schema unverified if TRS doesn't serve the
`FileWrapper` of the primary descriptor as JSON.

## Command-line interface

```bash
ga4gh-io-schema verify --schema examples/demo/ga4gh-io.schema.json \
  --trs-tool-id ga4gh-io-schema-demo --trs-version-id 1.0.0 \
  --descriptor-type WDL --descriptor examples/demo/demo.wdl
```

writes `The schema is verified (sha-256).`; with `--json`:

```json
{"verified": true, "mismatches": [], "compared": ["sha-256"]}
```

Options:

- `--schema PATH`: the IO schema (`-` for standard input).
- `--trs-tool-id`, `--trs-version-id`, `--descriptor-type`: the tool
  version and the descriptor type that the schema is used for; fields that
  are left out aren't compared.
- `--descriptor PATH`: the primary descriptor, whose bytes are hashed; or
  `--file-wrapper PATH`: its TRS `FileWrapper` as JSON (with `checksum`
  and `content`). At most one of the inputs can be `-`.
- `--require-verified`: fail also if the schema is unverified, e.g., in the
  CI of a workflow repository, to check that the schema names the checksum
  of the descriptor that it is published with.

A mismatch exits with status 1 and names each field, with both values
(with `--json`, the error has the members `verified`, `mismatches` and
`compared` of the result); so does an unverified schema with
`--require-verified`. Otherwise, an unverified schema exits with status 0
and says why it is unverified. With `--json`, each mismatch names the
`field` of `x-ga4gh-workflow`, its value in the `schema`, the value of the
`workflow`, the `algorithm` of a checksum (`null` for the other fields) and
the `message`, e.g., for another tool version:

```json
{
  "field": "trs_version_id",
  "schema": "1.0.0",
  "workflow": "1.1.0",
  "algorithm": null,
  "message": "x-ga4gh-workflow.trs_version_id is '1.0.0', not '1.1.0'."
}
```

## Python API

```python
from ga4gh_io_schema.workflow import check_workflow

result = check_workflow(
    schema,
    trs_tool_id=tool_id,
    trs_version_id=version_id,
    descriptor_type="WDL",
    descriptor=file_wrapper,  # GET .../{version_id}/WDL/descriptor
)
if result.mismatches:
    refuse_or_warn([mismatch.message for mismatch in result.mismatches])
elif not result.verified:
    mark_as_unverified()
```

Checksums can also be given without a `FileWrapper` (`checksums`, in the
format of TRS) or as the content of the descriptor (`content`, bytes or
text).

::: ga4gh_io_schema.workflow
