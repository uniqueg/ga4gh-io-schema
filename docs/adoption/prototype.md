# Prototype

The prototype shows on a single laptop, without outside services, that an IO
schema is enough to get from a workflow in a tool registry to a WES run
request: a portal finds the workflow in TRS, renders a form from its IO
schema and builds the request. Its parts live in `prototype/` of this
repository, apart from the specification, the package and its tools.

**A proof of concept, not a product:** the parts implement only what the
demonstration needs, aren't maintained like the `ga4gh-io-schema` package,
and aren't for deployment: no authentication, no TLS, no persistence (see
[What it doesn't do](#what-it-doesnt-do)).

## Prerequisites

- Git, and Docker with Docker Compose v2 (`docker compose`); `make`, for
  the short commands.
- Ports `8000` and `8080` free on `127.0.0.1` (or others, see
  [Testbed](testbed.md#run-it)).
- A web browser.
- Network access for the first build only: it pulls `python:3.13-alpine`
  and installs this package with its dependencies from PyPI. Nothing else
  leaves the laptop; no account, token or outside service is needed.

## Run it

One command, in a fresh clone of this repository:

```bash
git clone https://github.com/elixir-cloud-aai/ga4gh-io-schema.git
cd ga4gh-io-schema
make demo
```

`make demo` runs `docker compose -f prototype/compose.yaml up --detach
--build --wait`, with `TRS_URL` and `WES_URL` of the shell unset.
Compose builds one small image, starts two services and waits until both
are healthy:

| Service | Port | What it is |
| --- | --- | --- |
| `trs-stub` | `127.0.0.1:8080` | The [TRS stub](#trs-stub), with the demo workflow (`examples/demo/`), the [seeded workflows](testbed.md#the-seeded-workflows) (`examples/workflows/`) and their IO schemas, read from the checkout on every request. |
| `host` | `127.0.0.1:8000` | The [host of the form](form.md), which picks workflows from the stub (`--trs-url http://trs-stub:8080/ga4gh/trs/v2`). |

Then open <http://127.0.0.1:8000/>. `make demo-down` stops the stack and
removes its containers. The [testbed](testbed.md) page has the details:
other ports, the seeded workflows, and how to [play
around](testbed.md#play-around) with the schemas while the stack runs.

## Walkthrough

The page plays the portal: it knows a TRS and, optionally, a WES, and
nothing about any workflow. Each step uses only what the IO schema and
the GA4GH APIs give it.

### 1. Pick a workflow in TRS

![The page lists the workflows of the TRS stub; no form is shown before a
pick.](../assets/prototype/pick.png)

The list "Workflow in TRS" comes from `GET /tools` of the stub: one entry
per tool version and descriptor type. Pick "I/O Schema demo 1.0.0 (WDL)".
The host then lists the files of that tool version, finds the IO schema
(`ga4gh-io.schema.json` of type `OTHER`, next to the primary descriptor, as
the stub serves it; a file of type `IO_SCHEMA` would come first, see
[Discovery by clients](trs.md#discovery-by-clients)), fetches it, validates
it against the profile, and checks that its `x-ga4gh-workflow` names this
tool version and descriptor type, and the checksum of the primary
descriptor that the stub serves (with the [workflow block
check](../tools/verify.md)).

**What it shows:** a client finds the schema of any tool version through
the plain TRS API, by the [publishing convention](trs.md#publishing-convention)
alone; TRS needs no extension, and the schema says which workflow it
describes ([identity](../specification/identity.md#the-workflow-block)),
so a schema can't be applied to the wrong workflow by mistake.

### 2. Fill in the form

![The form of the demo, with a mapping quality of 61 and the schema's
error message under the field.](../assets/prototype/form-errors.png)

The form is rendered from the schema: titles, descriptions, the required
mark, a file reference, a slider with its bounds, a
choice as radio buttons, and defaults. Enter the reads of
`examples/demo/values.json` and a mapping quality of 61, and submit: the
schema's own message for the field appears ("The minimum mapping quality is
a whole number from 0 to 60"), and no run request is built.

**What it shows:** one generic form renders any workflow's inputs, with
[widgets](../specification/widgets.md) and messages
(`x-ga4gh-error-message`) chosen by the workflow's author, not by the
portal; values are checked against the schema, including the [rules for
file references](../specification/files.md), before anything is sent.

### 3. See the WES run request

![The form with valid values, and the WES run request under
it.](../assets/prototype/run-request.png)

Set the mapping quality to 20, pick `proper_pairs` and submit. The page
shows the run request that a WES gets:

```json
{
  "workflow_params": {
    "io_schema_demo.reads": "https://raw.githubusercontent.com/nf-core/test-datasets/3e548a3b34994380db1602506e0721fadbad6de1/data/genomics/sarscov2/illumina/bam/test.paired_end.bam",
    "io_schema_demo.min_mapq": 20,
    "io_schema_demo.read_filter": "proper_pairs"
  },
  "workflow_type": "WDL",
  "workflow_type_version": "1.1",
  "workflow_url": "http://trs-stub:8080/ga4gh/trs/v2/tools/ga4gh-io-schema-demo/versions/1.0.0/PLAIN_WDL/descriptor/demo.wdl"
}
```

**What it shows:** the [engine binding](../specification/engine-bindings.md)
turns the values into `workflow_params` in the shape that the WDL engine
expects (names qualified with the workflow name), and the schema gives
`workflow_type`, `workflow_type_version` and, with TRS, the `workflow_url`.
The user never chooses a workflow type or writes engine parameters, and
the portal has no code for this workflow or for WDL.

### 4. Send it to a WES (optional)

With `WES_URL` set (see below), a button "Send to WES" appears under a
valid run request. The host posts the request to `POST /runs` of the WES
and shows the run id and its state. Without `WES_URL`, nothing is ever
sent; the banner at the top of the page says so.

**What it shows:** the request is a plain WES `RunRequest`; any WES that
can fetch the `workflow_url` can run it.

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

Both URLs are fetched from inside the `host` container, where `127.0.0.1`
and `localhost` are the container itself, not your machine. A TRS or WES
that runs on your machine (e.g., a local TRS-Filer) needs an address that
the container can reach, such as the machine's address on the network, or
`host.docker.internal` where Docker provides it (Docker Desktop; on Linux,
only with `extra_hosts: ["host.docker.internal:host-gateway"]` added to the
`host` service). The service must also listen on that address: one bound
to `127.0.0.1` only (e.g., a port published as `127.0.0.1:8080:8080`)
can't be reached from the container; bind or publish it on the address
that `TRS_URL` or `WES_URL` names. The stub binds port 8080 on your machine
(`127.0.0.1:8080`), which is also the default port of TRS-Filer: run one of
them on another port.

```bash
TRS_URL=https://trs.example.org/ga4gh/trs/v2 \
  WES_URL=https://wes.example.org/ga4gh/wes/v1 \
  docker compose -f prototype/compose.yaml up --detach --build --wait
```

With the stub, the `workflow_url` names the stub inside the stack
(`http://trs-stub:8080/...`), which no WES outside can fetch: that is why
the stack sends nothing by default.

Without Docker, run the two parts directly (Python 3.11 or later, with this
package installed: `pip install -e .`), each in its own terminal:

```bash
python prototype/trs-stub/trs_stub.py
python prototype/host/form_host.py --trs-url http://127.0.0.1:8080/ga4gh/trs/v2
```

## What it doesn't do

- **No outputs:** it stops at the run request (or the run id and state);
  it doesn't follow a run or show its outputs. The [end-to-end
  demo](demo.md) normalises the outputs of a run with the [output
  normaliser](../tools/outputs.md).
- **Small workflows:** the stub serves the WDL demo and one small seeded
  workflow each in CWL, Nextflow and Snakemake, each a single file; none
  of them is run.
- **No security:** no authentication, no TLS, no credentials sent to a TRS
  or WES; the ports are bound to `127.0.0.1`. Keep it there.
- **No persistence and no service registry:** the TRS and the WES are
  given by URL; nothing is stored.

## Test it

CI's job "End-to-end test" starts the stack and runs
`tests/test_prototype_e2e.py`, which takes the path above twice: over the
host's HTTP API, as the page does, and in a browser (Chromium, driven by
Playwright), as a user does; it also gets the run requests of the seeded
workflows, and edits a schema of the checkout while the stack runs (and
restores it). Locally:

```bash
pip install -e ".[e2e]"
playwright install chromium
make demo
PROTOTYPE_URL=http://127.0.0.1:8000 \
  pytest -m e2e --no-cov tests/test_prototype_e2e.py
make demo-down
```

Without `PROTOTYPE_URL`, `pytest` skips these tests; without Playwright, it
skips the browser test (in CI, `PROTOTYPE_REQUIRE_BROWSER=1` makes that a
failure). `PROTOTYPE_BROWSER_CHANNEL=chrome` uses an
installed Chrome instead of Playwright's Chromium.

## Layout

All parts are in `prototype/` (see its `README.md`): the TRS stub in
`trs-stub/`, the host of the form and the page in `host/` ([Form proof of
concept](form.md)), and `Dockerfile` and `compose.yaml`; the `Makefile` at
the root has the short commands. The stub's container mounts `examples/`
of the checkout read-only. The image, from
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
  version are an error. Without `--workflow` and `--workflows-dir`, the
  stub serves `examples/demo/`.
- `--workflows-dir DIR` (repeatable): a directory whose subdirectories
  with a `ga4gh-io.schema.json` are workflows, as for `--workflow`, in the
  order of their names (e.g., `examples/workflows/`).
- `--reload`: read the files again on every request, so that edits, and
  new directories under `--workflows-dir`, show without a restart. A
  workflow that can't be read then, or that is a tool version served
  already, is left out and reported on standard error, also at the start
  (without `--reload`, it is an error). The stack runs the stub with
  `--workflow examples/demo --workflows-dir examples/workflows --reload`.
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
