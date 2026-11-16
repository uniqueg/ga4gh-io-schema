# Prototype

The prototype shows on a single laptop, without outside services, that an IO
schema is enough to get from a workflow in a tool registry to a WES run
request: a portal finds the workflow in TRS, renders a form from its IO
schema and builds the request. Its parts live in `prototype/` of this
repository, apart from the specification, the package and its tools.

**A proof of concept, not a product:** the parts implement only what the
demonstration needs, aren't maintained like the `ga4gh-io-schema` package,
and aren't for deployment: no authentication, no TLS, no persistence.

## TRS stub

`prototype/trs-stub/trs_stub.py` stands in for a tool registry. It serves
the workflow of the [end-to-end demo](demo.md) and its IO schema over the
TRS v2 API, following the [publishing convention](trs.md#publishing-convention)
of the profile. It needs Python and nothing else, not even this package:

```bash
python prototype/trs-stub/trs_stub.py
```

Then open <http://127.0.0.1:8080/ga4gh/trs/v2/tools>. Options:

- `--workflow DIR` (repeatable): a directory with an IO schema,
  `ga4gh-io.schema.json`, and the primary descriptor, under the file name
  of `primary_descriptor_path` of the schema's [workflow
  block](../specification/identity.md#the-workflow-block); the default is
  `examples/demo/`. The block gives the ids of the tool and the version
  (`trs_tool_id`, `trs_version_id`), the descriptor type and its version.
  Versions of the same tool id are served as one tool.
- `--host` and `--port`: the address to bind; the default is
  `127.0.0.1:8080`.

It implements these requests, under `/ga4gh/trs/v2`:

| Request | Response |
| --- | --- |
| `GET /tools` | The tools, each with its versions. |
| `GET /tools/{id}` | One tool. |
| `GET /tools/{id}/versions` | The versions of a tool. |
| `GET /tools/{id}/versions/{version_id}` | One version, with its descriptor type and version. |
| `GET .../{version_id}/{type}/files` | The primary descriptor (`PRIMARY_DESCRIPTOR`) and the IO schema (`OTHER`), with their paths. |
| `GET .../{version_id}/{type}/descriptor` | The primary descriptor as a `FileWrapper`, with its SHA-256 checksum, the one that `x-ga4gh-workflow.checksum` names. |
| `GET .../{version_id}/{type}/descriptor/{relative_path}` | A file by its path, e.g., `ga4gh-io.schema.json`, as a `FileWrapper`. |
| `GET .../{version_id}/PLAIN_{type}/descriptor[/{relative_path}]` | The same files as plain text. |

Anything else is `404` with a TRS `Error`. The stub doesn't implement the
other read endpoints of TRS (service info, tool classes, filters and
paging of `/tools`, containerfiles, tests, `?format=zip` of `files`), any
writes, or more than one descriptor type per tool version. It serves the
files as they are, without checking the schema against the profile or the
checksum against the descriptor: that is the client's job (step 2 and 3 of
the [guide for portals and clients](portals.md#guide-for-portals-and-clients)).
The `url` fields are built from the `Host` header of the request.

The host of the [form proof of concept](form.md) loads the schema from the
stub:

```bash
python examples/form/form_host.py --schema \
  http://127.0.0.1:8080/ga4gh/trs/v2/tools/ga4gh-io-schema-demo/versions/1.0.0/WDL/descriptor/ga4gh-io.schema.json
```

`tests/test_trs_stub.py` tests the endpoints and that the host loads the
schema from the stub.
