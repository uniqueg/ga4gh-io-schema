# Runsheet

How to present the [live demo](testbed.md) in about ten minutes: what to
prepare, what to show and say at each step, what the screen shows, and
what to do if a step fails. The demo runs on the presenter's laptop, from a
checkout of this repository, without a network once the image is built.

## Before the session (15 minutes, the day before or earlier)

1. In a fresh clone (or `git pull` in yours, on a clean working tree:
   `git status` lists nothing), build and start the demo once, so that the
   image is built while there is a network:

    ```bash
    git clone https://github.com/elixir-cloud-aai/ga4gh-io-schema.git
    cd ga4gh-io-schema
    make demo
    ```

    Expected: the last lines say `The demo is running: open
    http://127.0.0.1:8000/`. If a port is taken, use `make demo
    DEMO_PORT=18000 DEMO_TRS_PORT=18080` and the new port everywhere below.

2. Open <http://127.0.0.1:8000/> and go through the steps below once.
3. Open these in tabs, in this order: the page; the
   [testbed](testbed.md) page (the table of parts, as a backup slide); and
   an editor with `examples/workflows/greetings-nextflow/ga4gh-io.schema.json`
   and `examples/workflows/word-count-cwl/wc.cwl`.
4. Keep `examples/demo/values.json` at hand: the URL of the reads is long
   to type: copy it from the file.
5. Stop the stack with `make demo-down`. The image stays: `make
   demo-start` starts it again in seconds, without building and without a
   network.

## On the day (5 minutes before)

1. `make demo-start` in the checkout (or `make demo`, with a network).
   Expected: "The demo is running".
2. Reload the page: the list "Workflow in TRS" has four workflows.
3. Zoom the browser to 125–150% for the room; close other tabs and
   notifications.

## The demo (10 minutes)

| Time | Step | What to do | What the screen shows | What to say |
| --- | --- | --- | --- | --- |
| 0:00 | 1. The portal | Show the page, open the list "Workflow in TRS". | A banner (no WES, nothing is sent) and four workflows: the WDL demo and one workflow each in CWL, Nextflow (NFL) and Snakemake (SMK). | The page plays a portal that knows a TRS and nothing about any workflow. The list is `GET /tools` of a TRS stub. |
| 1:00 | 2. Discovery | Pick "I/O Schema demo 1.0.0 (WDL)". | The form: aligned reads, a slider for the mapping quality, radio buttons for the read filter ([screenshot](../assets/prototype/form-errors.png)). | The host found `ga4gh-io.schema.json` next to the descriptor by the publishing convention, validated it against the profile, and checked that it names this tool version and the checksum of `demo.wdl`. TRS needed no change. |
| 2:30 | 3. Validation | Paste the reads URL, set the mapping quality to 61, Submit. | Under the slider: "The minimum mapping quality is a whole number from 0 to 60"; no run request. | The rules and the message come from the workflow's author, in the schema; the portal has none of its own. |
| 3:30 | 4. Run request | Set 20, pick `proper_pairs`, Submit. | The WES run request: `workflow_params` with names like `io_schema_demo.min_mapq`, `workflow_type` `WDL`, `workflow_url` the TRS URL of `demo.wdl` ([screenshot](../assets/prototype/run-request.png)). | The engine binding for WDL qualified the names; the user never chose a workflow type or wrote engine parameters. It isn't sent: there is no WES in the demo. |
| 4:30 | 5. Other languages | Pick "Greetings 1.0.0 (NFL)", put three names in, pick `fr`, tick "Shout", Submit. Then pick "Little report" and "Count words" briefly. | A text area (one name per line), radio buttons, a slider, a checkbox, "Advanced"; the run request with plain Nextflow parameters ([screenshot](../assets/prototype/greetings.png)). The report has a date picker and a colour picker; Count words a file field and a dropdown. | Same form, same host, four languages; the bindings differ (WDL qualifies names, CWL turns files into `File` objects), the schema keywords don't. |
| 6:30 | 6. Play: change the form | In the editor, in the Greetings schema, under `"times"`, change `"maximum": 5` to `"maximum": 10` and `"x-ga4gh-ui-widget": "slider"` to `"x-ga4gh-ui-widget": "number"` (see [the edits](#the-edits)). Save, reload the page, pick "Greetings". | "How many times" is a number field now, and 9 is accepted. | The schema is the contract: the author edits it, every portal follows. No rebuild, no restart. |
| 7:30 | 7. Play: drift | At the end of `wc.cwl`, add the line `# changed`. Save, pick "Count words". | "The schema may not match the workflow: x-ga4gh-workflow.checksum (sha-256) is …, but the primary descriptor has …"; no form ([screenshot](../assets/prototype/drift.png)). | The schema names the checksum of the descriptor it describes; when the workflow changes and the schema doesn't, the client refuses it instead of rendering a wrong form. |
| 8:30 | 8. Wrap up | Undo both edits (or `git checkout -- examples/workflows`), reload. Show the testbed page's table of parts. | The forms are back. | Real: the profile, validator, workflow block check, request builder, form. Mocked: the TRS. Absent: a WES, runs and outputs. What we ask the work stream: see the [open questions](../roadmap.md#open-questions). |

Afterwards: `make demo-down`, and `git status` to check that nothing is
left changed (`git checkout -- examples/workflows` restores the files;
`git clean -fd examples/workflows` deletes copied workflows).

### The edits

Step 6, in `examples/workflows/greetings-nextflow/ga4gh-io.schema.json`,
the input `times` before:

```json
"minimum": 1,
"maximum": 5,
"default": 1,
"x-ga4gh-ui-widget": "slider"
```

and after:

```json
"minimum": 1,
"maximum": 10,
"default": 1,
"x-ga4gh-ui-widget": "number"
```

Only the two values change: keep the commas and quotes, or the workflow
drops out of the list until the file is valid JSON again. Step 7, the last
line of `examples/workflows/word-count-cwl/wc.cwl`:

```text
# changed
```

## If something fails

| Symptom | Likely cause | What to do |
| --- | --- | --- |
| `make demo` stops with `address already in use` | Port 8000 or 8080 is taken (a local TRS-Filer, a port forward, an earlier stack of another checkout). | `make demo DEMO_PORT=18000 DEMO_TRS_PORT=18080`, then use port 18000. |
| `make demo` fails while building, e.g., can't pull `python:3.13-alpine` or reach PyPI | No network. | If the image was built before: `make demo-start`. Otherwise use a network (e.g., a phone hotspot) for the build; it takes a minute or two. Without one: show the screenshots of the [prototype](prototype.md#walkthrough) page and this page. |
| `make: command not found` | No `make` (e.g., on Windows). | `docker compose -f prototype/compose.yaml up --detach --build --wait` (offline, after a build: `up --detach --no-build --pull never --wait`), and `docker compose -f prototype/compose.yaml down` to stop. |
| `docker: command not found`, or the daemon isn't running | Docker isn't installed or not started. | Start Docker Desktop (or the daemon) and run `make demo` again. Without Docker: `pip install -e .` in the checkout, then, in two terminals, `python prototype/trs-stub/trs_stub.py --workflow examples/demo --workflows-dir examples/workflows --reload` and `python prototype/host/form_host.py --trs-url http://127.0.0.1:8080/ga4gh/trs/v2`. |
| The page says `Can't list the workflows of http://trs-stub:8080/…` | The stub isn't up (yet), or crashed. | `make demo-logs` to see why; `make demo-down` and `make demo` to restart. |
| A workflow is missing from the list | Its schema isn't valid JSON after an edit, or two directories have the same tool id. | `make demo-logs` names the file; undo the edit (`git checkout -- examples/workflows`) and reload. |
| "The schema may not match the workflow" for a workflow you didn't mean to change | A descriptor was edited and not restored. | `git checkout -- examples/workflows`, or `make demo-checksums` to accept the edit. |
| An edit doesn't show | The page wasn't reloaded, or the file wasn't saved, or the edit is in the image, not in `examples/` (e.g., `prototype/`). | Save, reload the page and pick the workflow again. Changes to `prototype/` need `make demo` (rebuild). |
| The page is blank or the form doesn't render | The browser blocks scripts, or an old cache. | Hard reload (Ctrl+Shift+R); try another browser (Chrome, Firefox). The host's API works without a browser: `curl http://127.0.0.1:8000/api/config`. |
| The list of workflows is empty or lacks some, and `make demo-logs` shows "Permission denied" | The checkout isn't readable by other users (e.g., a umask of 077), and the stub runs as an unprivileged user. | `chmod -R a+rX examples` in the checkout, then reload the page. |
| A copied workflow stays in the list after `git checkout -- examples/workflows` | New directories aren't tracked, so `git checkout` leaves them. | `git status` lists them; delete them, or `git clean -fd examples/workflows` (this deletes every untracked file there). |
