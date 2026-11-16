# Prototype

The prototype shows on a single laptop, without outside services, that an IO
schema is enough to get from a workflow in a tool registry to a WES run
request: a portal finds the workflow in TRS, renders a form from its IO
schema and builds the request. Its parts live in `prototype/` of this
repository, apart from the specification, the package and its tools.

**A proof of concept, not a product:** the parts implement only what the
demonstration needs, aren't maintained like the `ga4gh-io-schema` package,
and aren't for deployment: no authentication, no TLS, no persistence.

## Run it

With Docker and Docker Compose, in a clone of this repository:

```bash
docker compose -f prototype/compose.yaml up --build
```

Compose builds one small image and starts two services:

| Service | Port | What it is |
| --- | --- | --- |
| `trs-stub` | `127.0.0.1:8080` | The [TRS stub](#trs-stub), with the demo workflow (`examples/demo/`) and its IO schema. |
| `host` | `127.0.0.1:8000` | The [host of the form](form.md), which picks workflows from the stub (`--trs-url http://trs-stub:8080/ga4gh/trs/v2`). |

Then open <http://127.0.0.1:8000/>:

1. **Pick the workflow** "I/O Schema demo 1.0.0 (WDL)": the list comes from
   `GET /tools` of the stub. The host finds the IO schema in the files of
   the tool version (`ga4gh-io.schema.json` of type `OTHER` next to the
   primary descriptor), checks it against the profile and checks that it
   names that tool version and descriptor type.
2. **Fill in the form** that the schema renders, e.g., with the values of
   `examples/demo/values.json`. Wrong values get the messages of the
   schema (`x-ga4gh-error-message`).
3. **See the WES run request**: `workflow_params` in the shape of the WDL
   engine, `workflow_type`, `workflow_type_version`, and the TRS URL of the
   primary descriptor as `workflow_url`. Nothing in the portal is specific
   to the workflow or its language.

`docker compose -f prototype/compose.yaml down` stops it.

### Point it at a real TRS or WES

Two environment variables change the stack, without changing a file:

- `TRS_URL`: the base URL of another TRS API to pick workflows from, e.g.,
  a TRS-Filer instance with the demo registered (see [End-to-end
  demo](demo.md)). Only tool versions whose files include an IO schema can
  be filled in.
- `WES_URL`: the base URL of an existing WES API. The page then offers
  "Send to WES" under a valid run request and shows the run id and state.
  The WES must be able to fetch the `workflow_url`, so use it with a
  `TRS_URL` that the WES can reach: the stub is reachable only inside the
  stack. The host sends no credentials, so the WES must accept anonymous
  runs.

```bash
TRS_URL=https://trs.example.org/ga4gh/trs/v2 \
  WES_URL=https://wes.example.org/ga4gh/wes/v1 \
  docker compose -f prototype/compose.yaml up --build
```

Without Docker, run the two parts directly (Python 3.11 or later, with this
package installed: `pip install -e .`), each in its own terminal:

```bash
python prototype/trs-stub/trs_stub.py
python prototype/host/form_host.py --trs-url http://127.0.0.1:8080/ga4gh/trs/v2
```

### Test it

CI's job "End-to-end test" starts the stack and runs
`tests/test_prototype_e2e.py`, which takes the path above twice: over the
host's HTTP API, as the page does, and in a browser (Chromium, driven by
Playwright), as a user does. Locally:

```bash
pip install -e ".[e2e]"
playwright install chromium
docker compose -f prototype/compose.yaml up --detach --build --wait
PROTOTYPE_URL=http://127.0.0.1:8000 \
  pytest -m e2e --no-cov tests/test_prototype_e2e.py
docker compose -f prototype/compose.yaml down
```

Without `PROTOTYPE_URL`, `pytest` skips these tests; without Playwright, it
skips the browser test (in CI, `PROTOTYPE_REQUIRE_BROWSER=1` makes that a
failure). `PROTOTYPE_BROWSER_CHANNEL=chrome` uses an
installed Chrome instead of Playwright's Chromium.

### Layout

All parts are in `prototype/` (see its `README.md`): the TRS stub in
`trs-stub/`, the host of the form and the page in `host/` ([Form proof of
concept](form.md)), and `Dockerfile` and `compose.yaml`. The image, from
`python:3.13-alpine` with this package installed, runs as an unprivileged
user; the containers are read-only, without capabilities, and their ports
are bound to `127.0.0.1`. The root `.dockerignore` keeps the build context
to the files that the image needs.

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
  `ga4gh-io.schema.json`, and the primary descriptor, at the
  `primary_descriptor_path` of the schema's [workflow
  block](../specification/identity.md#the-workflow-block), which must be a
  file name (no directories); the default is `examples/demo/`. The block
  gives the ids of the tool and the version (`trs_tool_id`,
  `trs_version_id`), the descriptor type and its version. Versions of the
  same tool id are served as one tool; two directories for the same tool
  version are an error.
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
| `GET .../{version_id}/{type}/descriptor` | The primary descriptor as a `FileWrapper`, with the SHA-256 checksum of the file (for the demo, the one that `x-ga4gh-workflow.checksum` names). |
| `GET .../{version_id}/{type}/descriptor/{relative_path}` | A file by its path, e.g., `ga4gh-io.schema.json`, as a `FileWrapper`. |
| `GET .../{version_id}/PLAIN_{type}/descriptor[/{relative_path}]` | The same files as plain text. |

Any other `GET` is `404` with a TRS `Error`; other methods get the default
error pages of Python's `http.server`. The stub doesn't implement the other
read endpoints of TRS (service info, tool classes, containerfiles, tests),
query parameters (filters and paging of `/tools`, `?format=zip` of `files`:
they are ignored), any writes, or more than one descriptor type per tool
version. It serves the files byte for byte, without checking the schema
against the profile or the checksum against the descriptor: that is the
client's job (steps 2 and 3 of the [guide for portals and
clients](portals.md#guide-for-portals-and-clients)). The `url` fields are
built from the `Host` header of the request.

The host of the [form proof of concept](form.md) lists the workflows of the
stub and loads their schemas from it (`--trs-url`), or loads one schema from
its URL:

```bash
python prototype/host/form_host.py --schema \
  http://127.0.0.1:8080/ga4gh/trs/v2/tools/ga4gh-io-schema-demo/versions/1.0.0/WDL/descriptor/ga4gh-io.schema.json
```

`tests/test_trs_stub.py` tests the endpoints and that the host loads the
schema from the stub.
