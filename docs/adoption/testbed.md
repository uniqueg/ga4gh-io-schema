# Testbed

The live demo of the profile is the [prototype](prototype.md) of this
repository: a TRS stub that serves the demo workflow and three seeded
workflows, the host of a generic form, and the WES run request that the
form builds. Everything it needs is in the repository, and it runs on one
laptop. It is a proof of concept, not an implementation within a real
stack, and it is self-contained: anybody who checks out the repository can
run it on their own, without tokens, accounts or deployed services, and
play around with it.

This page describes the testbed as a whole: how to run it, how to play
around with it, its parts, what is real and what is mocked, and its
limits. The [prototype](prototype.md#walkthrough) page walks through the
demo step by step, the [runsheet](runsheet.md) is the script for
presenting it in about ten minutes, and the
[evaluation](prototype-evaluation.md) says what it showed about the
profile.

## Run it

**Prerequisites:**

- Git, and Docker with Docker Compose v2 (`docker compose`). CI runs the
  stack on GitHub's `ubuntu-latest` runner (the `ubuntu-26.04` image in
  November 2026), with the Docker Engine and Compose that it ships; any
  recent Docker with Compose v2 should do.
- `make` (GNU Make, or the `make` of macOS), or type the Compose command
  that step 2 names.
- Ports `8000` and `8080` free on `127.0.0.1`, or two other ports (see
  step 2).
- A web browser.
- Network access for the first build: it pulls `python:3.13-alpine` and
  installs this package from the checkout, with its dependencies from
  PyPI. Once the image is built, the stack runs offline.

**Steps,** from any directory:

1. Clone the repository and enter it:

    ```bash
    git clone https://github.com/elixir-cloud-aai/ga4gh-io-schema.git
    cd ga4gh-io-schema
    ```

2. Build the image, start the stack and wait until it is healthy (the
   first build takes a minute or two):

    ```bash
    make demo
    ```

    It prints the URL of the page when the stack is up. Without `make`:

    ```bash
    env -u TRS_URL -u WES_URL docker compose -f prototype/compose.yaml up --detach --build --wait
    ```

    `env -u` makes sure that `TRS_URL` and `WES_URL` of your shell, if set,
    don't point the stack at another TRS or WES (see [Point it at a real
    TRS or WES](prototype.md#point-it-at-a-real-trs-or-wes)); `make demo`
    does the same.

    If a port is in use (e.g., port 8080 by a local TRS-Filer or a port
    forward), Compose stops with `address already in use`. Pick other
    ports (without `make`, set `DEMO_PORT` and `DEMO_TRS_PORT` in the
    environment of `docker compose`):

    ```bash
    make demo DEMO_PORT=18000 DEMO_TRS_PORT=18080
    ```

    The host reaches the stub inside the stack, so the demo doesn't change;
    open the page on the new port (here <http://127.0.0.1:18000/>).

3. Open <http://127.0.0.1:8000/> and follow the
   [walkthrough](prototype.md#walkthrough): pick "I/O Schema demo 1.0.0
   (WDL)"; a mapping quality of 61 gives the schema's error message, 20
   with `proper_pairs` gives the run request. Then pick the [seeded
   workflows](#the-seeded-workflows).

4. Stop the stack and remove its containers and network:

    ```bash
    make demo-down
    ```

    `make demo-start` starts it again from the image that `make demo` built,
    without building, so without a network. `make demo-clean` removes the
    image too (the next `make demo` builds it
    again). While the stack runs, `make demo-logs` follows the logs of its
    two services, `trs-stub` and `host`. `make` alone lists the targets.

## The seeded workflows

Besides the WDL demo, the stub serves one small workflow in each other
language of the profile, from `examples/workflows/`. Each is a directory
with its primary descriptor, its IO schema (`ga4gh-io.schema.json`) and
example input values (`values.json`, which the stub doesn't serve):

| In the list | Directory | Language | What the form shows |
| --- | --- | --- | --- |
| I/O Schema demo 1.0.0 (WDL) | `examples/demo/` | WDL 1.1 | A file reference with an example, a slider with bounds and an error message, radio buttons. |
| Count words 1.0.0 (CWL) | `examples/workflows/word-count-cwl/` | CWL v1.2 | A required file reference (`https` only), a dropdown with a default. The run request has the file as a CWL `File` object. |
| Greetings 1.0.0 (NFL) | `examples/workflows/greetings-nextflow/` | Nextflow DSL2 | A list of names, one per line, each checked by a pattern, with an error message; radio buttons; a slider; a checkbox; a hidden input under "Advanced". |
| Little report 1.0.0 (SMK) | `examples/workflows/report-snakemake/` | Snakemake | A text with a length limit and an error message, a date picker, a text area, a colour picker. |

The form, the host and the stub have no code for any of these workflows or
languages: everything that the page shows comes from the IO schemas.

## Play around

The stub reads the workflows from the checkout, which is mounted read-only
into its container, on every request (`--reload`). Edits show when you
reload the page, without a rebuild or a restart:

- **Change the form:** in
  `examples/workflows/greetings-nextflow/ga4gh-io.schema.json`, set the
  `maximum` of `times` to `10`, or its `x-ga4gh-ui-widget` from `slider` to
  `number`; change the `title` of an input; or add a language to the
  `enum` of `language`. Save, reload the page and pick "Greetings" again.
- **Change a rule and its message:** change the `pattern` or the
  `x-ga4gh-error-message` of `names`, and submit a name that breaks it.
- **Add an input:** add a property to `properties` of `inputs`, e.g.,
  `"punctuation": {"type": "string", "title": "Punctuation", "enum": ["!", "."], "default": "!"}`,
  and see it in the form and in `workflow_params`.
- **Break the schema:** give an input an `x-ga4gh-` keyword that the
  profile doesn't have, e.g., `"x-ga4gh-colour": "red"`: the page reports
  that the schema doesn't comply with the profile and shows no form. A
  file that isn't JSON makes the workflow disappear from the list;
  `make demo-logs` shows why.
- **Change the workflow, see drift:** edit a primary descriptor, e.g., add
  a comment line to `examples/workflows/word-count-cwl/wc.cwl`. Its
  checksum no longer matches the one that the schema names, and the host
  refuses the schema ("The schema may not match the workflow"). Set the
  checksums again with `make demo-checksums` (or
  `python3 examples/demo/checksums.py`), and the form is back.
- **Add a workflow:** copy a directory under `examples/workflows/`, change
  `trs_tool_id` in the `x-ga4gh-workflow` of its schema, and reload: it is
  in the list. Of two directories with the same tool id and version, the
  second is left out, and the logs say so.

The schema of the WDL demo (`examples/demo/`) is generated by
`examples/demo/build_schema.py` and checked by the tests: play with the
seeded workflows instead. When you're done, restore the checked-in files
with `git checkout -- examples/`, and delete copied workflows (`git
clean -fd examples/workflows` deletes every untracked file there); broken
or duplicate workflows are left out also when the stack starts again. The
tests
(`tests/test_seeded_workflows.py`) check that the seeded schemas comply,
that their checksums are current and that their values give run requests.

## The parts

| Part | Where | What it does | Real or mocked |
| --- | --- | --- | --- |
| Profile | `schemas/` | The meta-schema and vocabularies that the IO schema is validated against. | Real: the schemas of version 0.3.0. |
| Demo workflow | `examples/demo/demo.wdl` | A WDL 1.1 workflow that filters, sorts and indexes aligned reads and writes a report. | Real, but never run by the testbed. |
| IO schema | `examples/demo/ga4gh-io.schema.json` | The inputs and outputs of the workflow, generated by `build_schema.py` from the output of [`convert wdl`](../tools/convert-wdl.md) and `schema.overlay.json`. | Real. |
| Seeded workflows | `examples/workflows/` | One small workflow each in CWL, Nextflow and Snakemake, with an IO schema written by hand (see [The seeded workflows](#the-seeded-workflows)). | Real descriptors and schemas, but never run. |
| TRS stub | `prototype/trs-stub/trs_stub.py`, service `trs-stub` | Serves the tool `ga4gh-io-schema-demo`, version `1.0.0`, descriptor type `WDL`, with two files from `examples/demo/`: the primary descriptor `demo.wdl` and the IO schema `ga4gh-io.schema.json` (type `OTHER`, by the [publishing convention](trs.md#publishing-convention)); and each seeded workflow the same way. It reads the files of the checkout on every request. | Mocked: a few read endpoints of TRS v2, not a TRS implementation (see [TRS stub](prototype.md#trs-stub)). |
| Form host | `prototype/host/`, service `host` | Lists the workflows of a TRS (`--trs-url`), finds and fetches the IO schema of the one picked, validates it against the profile, checks its workflow block (ids, descriptor type, checksum of the primary descriptor; see [workflow block check](../tools/verify.md)), renders the form, reports wrong values with the schema's messages, and builds the WES run request. | Real: the validator, the workflow block check and the request builder of the `ga4gh-io-schema` package, and the [form proof of concept](form.md) of this repository. |
| WES run request | Shown under the form | `workflow_params` from the engine binding of the language (for WDL, names qualified with the workflow name), `workflow_type` and `workflow_type_version` from the workflow block, and the TRS URL of the plain primary descriptor as `workflow_url`. | Real, but not sent. |
| WES | Not part of the testbed | With `WES_URL` set, the host offers "Send to WES" and posts the request to `POST /runs`; without it, nothing is sent, and the page says so. | Absent. |

The run request for the values of the walkthrough:

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

## Real and mocked

- **Real:** the profile, its schemas, the validator, the converters (which
  produced the IO schema of the WDL demo), the workflow block check, the
  request builder, and the form. They are the same code that the package
  and its tests use.
- **Mocked:** the TRS. The stub implements the few read endpoints that a
  client needs to find a workflow and its IO schema, and nothing else (no
  writes, no service info, no paging).
- **Absent:** a WES, a workflow run and its outputs. The testbed stops at
  the run request. The run log in `examples/demo/expected/run-log.json`
  isn't a recorded run: it is written from the source code of a WES
  implementation, for the tests of the [output
  normaliser](../tools/outputs.md).

## Limits

- **No authentication, no TLS, no deployed services:** the ports are bound
  to `127.0.0.1`, and the TRS is a stub. The demo says nothing about how
  the profile works with access control or with real registries.
- **Small workflows, one file each:** one workflow per language, each a
  single primary descriptor. The seeded workflows are written for the
  demo, and their schemas by hand, not by the converters. Multi-file
  workflows and the converters of CWL, Nextflow and Snakemake are tested
  in the package, not in the testbed.
- **No runs:** the testbed shows that an IO schema is enough to get from a
  workflow in TRS to a valid WES run request, not that a WES runs it or
  that the outputs fit the schema.

For the conclusions, this means: they hold for discovering, checking and
rendering an IO schema and for building run requests; they are not
evidence for execution, outputs, security in deployment or real-world
workflows (see [Limits of the
prototype](prototype-evaluation.md#limits-of-the-prototype)).

## How it is tested

CI's job "End-to-end test" runs the same stack from a fresh checkout
(`make demo`) and `tests/test_prototype_e2e.py`, which takes the path of
the walkthrough over the host's HTTP API and in a browser (Chromium,
driven by Playwright): the list of workflows, the IO schema, the error
message for a mapping quality of 61 and the run request above. It also
gets the run request of each seeded workflow from its example values, and
edits a schema of the checkout while the stack runs, as in [Play
around](#play-around). To run it locally, see [Test
it](prototype.md#test-it).

A demo of the profile with deployed services, e.g., the components of a
platform, is out of scope here; the [end-to-end demo](demo.md) is a guide
for adopters, not part of the testbed.
