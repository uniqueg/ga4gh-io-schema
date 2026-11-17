# TRS discovery

The `ga4gh_io_schema.trs` module finds the IO schema of a TRS tool version
among its files, by the rules of [Matching file
entries](../adoption/trs.md#matching-file-entries): the one entry of type
`IO_SCHEMA`, or else the entry of type `OTHER` at `ga4gh-io.schema.json` in
the directory of the primary descriptor, comparing `file_type` and
normalised `path` only. It does no HTTP: the caller lists the files, and
fetches and checks the schema (see [Discovery by
clients](../adoption/trs.md#discovery-by-clients)).

```python
from ga4gh_io_schema.trs import find_schema_file

# The answer of GET /tools/{id}/versions/{version_id}/WDL/files
files = [
    {"path": "./main.wdl", "file_type": "PRIMARY_DESCRIPTOR", "checksum": []},
    {"path": "./ga4gh-io.schema.json", "file_type": "OTHER"},
]
found = find_schema_file(files)
# SchemaFile(path='./ga4gh-io.schema.json', file_type='OTHER'): fetch it
# from .../WDL/descriptor/{found.path}, percent-encoded
```

`None` means that the tool version has no IO schema for the descriptor
type (or several files of type `IO_SCHEMA`). The test vectors of the rules
are in `tests/vectors/trs-files/cases.json`. The [demo with
TRS-Filer](../adoption/demo-trs-filer.md) uses the module in a complete
client (`examples/demo/trs_client.py`).

## API reference

::: ga4gh_io_schema.trs
