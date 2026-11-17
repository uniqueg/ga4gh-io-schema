# Form proof of concept

`prototype/host/` holds a minimal form and a host for it: an IO schema is
enough to render a run form, to validate the values with the schema's own
error messages, and to turn them into a WES run request. It depends on
nothing but this repository: no Cloud Components, no portal, no JavaScript
framework, and no build step.

**A proof of concept, not a product:** the form and the host show that the
profile works on its own. They aren't a reference client, aren't maintained
like the `ga4gh-io-schema` package, and aren't for deployment: the host has
no authentication, serves one schema, and submits a run only if it is
given the URL of a WES and the user asks for it. Portals adopt the
profile with their own components (see [Portals and clients](portals.md)).

## Run it

To run it with the TRS stub, as the whole prototype with Docker Compose, see
[Prototype](prototype.md#run-it).

In a checkout of this repository, with the package installed (`pip install
-e .`), one command starts the host for the schema of the [end-to-end
demo](demo.md):

```bash
python prototype/host/form_host.py
```

Then open <http://127.0.0.1:8000/>. The page shows a form for the inputs of
the demo workflow: a field for the aligned reads, a slider with a number
field for the minimum mapping quality, and a choice of read filters.

- Enter a mapping quality of 61 and submit: the field shows "The minimum
  mapping quality is a whole number from 0 to 60", the
  `x-ga4gh-error-message` of the schema, and the form says that `reads` is
  required.
- Enter the values of `examples/demo/values.json` (the URL of the reads, 20,
  `proper_pairs`) and submit: the page shows the WES run request, with the
  `workflow_params` of [Run it from the command
  line](demo.md#2-run-it-from-the-command-line) (the names qualified by the
  WDL entry point), `workflow_type` `WDL`, `workflow_type_version` `1.1`
  and the `workflow_url` (see `--trs-url`).

Options:

- `--schema PATH_OR_URL`: another default IO schema, as a file or an
  `http(s)` URL, e.g., the TRS URL of the file `ga4gh-io.schema.json` of a
  tool version
  (`.../tools/{id}/versions/{version_id}/{type}/descriptor/ga4gh-io.schema.json`,
  see [Discovery by clients](trs.md#discovery-by-clients)); a `FileWrapper`
  must have the schema in `content`. With `--trs-url` and without
  `--schema`, there is no default schema: users pick a workflow.
- `--allow-scheme SCHEME` (repeatable): the allow-list of URI schemes of
  file references, as for [`wes-params`](../tools/wes-params.md); the
  default is `drs` and `https`.
- `--trs-url URL`: the base URL of a TRS API (e.g.,
  `http://127.0.0.1:8080/ga4gh/trs/v2` for the [TRS
  stub](prototype.md#trs-stub)). The page lists its tool versions, per
  descriptor type, and users pick one: the host takes the IO schema from
  the files of the tool version (the file of type `IO_SCHEMA`, or else
  `ga4gh-io.schema.json` of type `OTHER` in the directory of the primary
  descriptor, matched as [Matching file
  entries](trs.md#matching-file-entries) says), validates it against the
  profile, and rejects it if its `x-ga4gh-workflow` names another tool,
  version or descriptor type, or a checksum that the primary descriptor
  doesn't have (step 2 of the guide, with the [workflow block
  check](../tools/verify.md)). A schema whose checksum can't be
  compared is used, unverified, without a note on the page.
  The `workflow_url` of the run request is the TRS URL of the plain
  primary descriptor, by the path that TRS lists for it
  (`.../PLAIN_{type}/descriptor/{path}`, see [Workflow URLs in
  TRS](../specification/engine-bindings.md#workflow-urls-in-trs)). For the
  default schema, the `workflow_url` is the same URL for the tool version
  that `x-ga4gh-workflow` names (`trs_tool_id`, `trs_version_id`), by its
  `primary_descriptor_path` if it has one. Without `--trs-url`, or if the
  schema names no tool version, the `workflow_url` is
  `primary_descriptor_path`, which a WES resolves against files attached
  to the request; the host attaches none. Without either, valid values get
  an error that no workflow URL is known.
- `--wes-url URL`: the base URL of a WES API (e.g.,
  `https://wes.example.org/ga4gh/wes/v1`). With it, the page shows a
  button "Send to WES" under a valid run request: the host posts the
  request to `POST /runs` of the WES, as `multipart/form-data` without
  attachments, and shows the run id and the state from
  `GET /runs/{run_id}/status`. Without it, nothing is ever sent. The WES
  must be able to fetch the `workflow_url` and the input files, so with a
  default schema, `--wes-url` needs `--trs-url` and a schema that names its
  TRS tool version; the host refuses to start otherwise. Workflows picked
  in the TRS always have a TRS `workflow_url`. An empty `--wes-url` is the
  same as none.
- `--host` and `--port`: the address to bind; the default is
  `127.0.0.1:8000`.

The host validates the schema against the profile when it starts, and
exits with status 1 if the schema can't be read or doesn't comply. It
prints the `workflow_url` that it uses and whether a WES is configured.

## How it works

| File | What it is |
| --- | --- |
| `form_host.py` | The host: Python standard library and this package. Serves the page and the schema, validates the values, builds the run request and, if configured, submits it. |
| `form.js` | The logic of the form, without the DOM: the control of each input, hidden inputs, and how the text of a control becomes a value. |
| `io-schema-form.js` | `<io-schema-form>`, a plain web component that renders the fields of `form.js` and emits the values. |
| `index.html`, `app.js`, `form.css` | The page: fetches the schema, renders the form, sends the values to the host and shows the run request, the run, or the errors. |

The steps of the [guide for portals and clients](portals.md#guide-for-portals-and-clients)
are split between the two:

- **The form** renders the inputs (step 4) with the widgets of [Input
  widgets](../specification/widgets.md#input-widgets), and falls back to
  the type, `format` and `enum` of an input for widgets that it doesn't know
  or that don't fit. Hidden inputs go under "Advanced", except those that
  users must set; "Advanced" opens when an input in it has an error. An
  optional object whose members all have their defaults is left out. Text
  from the schema is set as text, never as HTML (step 5). Inputs that the
  user leaves empty are left out of the values; defaults are prefilled.
- **The host** validates the schema offline (step 3), validates the values
  against `inputs` with the [Python validator](../tools/validator.md)
  (step 7), checks the file reference values (step 6) and builds the
  run request with [`wes-params --request`](../tools/wes-params.md)
  (step 8).
  Every failure gets the `x-ga4gh-error-message` that covers it, by the
  rules of [Error messages](../specification/keywords.md#error-messages),
  or the validator's message; the form shows each error next to its input,
  and errors of the values as a whole (e.g., a missing required input)
  above the button.

The host's API, for the page:

- `GET /api/schema`: the IO schema.
- `GET /api/config`: `{"wes": true}` if a WES is configured, else
  `{"wes": false}`; with a TRS, also its `workflows` (`tool_id`,
  `version_id`, `descriptor_type`, `name`), or an empty list and
  `trs_error` if they can't be listed.
- With a TRS, the query `?tool=...&version=...&type=...` picks a workflow
  for `/api/schema`, `/api/params` and `/api/runs`; a workflow that can't
  be loaded gets `502`, and a request without a pick and without a
  default schema gets `404`.
- `POST /api/params` with the values as JSON: `200` with
  `{"run_request": {"workflow_params": {...}, "workflow_type": "WDL",
  "workflow_type_version": "1.1", "workflow_url": "..."}}`, or `400` with
  `{"errors": [{"pointer": "/min_mapq", "message": "..."}]}`, where
  `pointer` is the location of the value in the values (JSON Pointer).
- `POST /api/runs` with the values as JSON: as `/api/params`, and submits
  the request to the WES: `200` with `{"run_request": {...}, "run_id":
  "...", "state": "QUEUED"}` (`state` is `null` if it can't be read),
  `404` if no WES is configured, or `502` if the WES fails, each with an
  error of the request as a whole (`pointer` `""`).

`tests/test_form_host.py` tests the host (values to the run request, the
error messages, the HTTP API, and the submission to a local fake WES), and
`tests/js/form.test.mjs` the logic of the form (controls, hidden inputs,
values from the controls); see
[Development](../development.md#javascript-tests-nodejs).

## Known limits

What the proof of concept leaves out, on purpose:

- **Minimal submission:** it sends the four fields of the run request
  and nothing else: no `tags`, no `workflow_engine_parameters`, no
  attachments, and no authentication, so it works only with a WES that
  accepts anonymous runs and can fetch the `workflow_url`; it reads the
  state once and doesn't follow the run. The [end-to-end demo](demo.md)
  submits runs to Conquest from the command line (`conquest.py`), with the
  engine parameters that Conquest needs.
- **No checks of the workflow block of the default schema** (step 2 of
  the guide): only schemas picked in a TRS are checked. The
  engine binding comes from `x-ga4gh-workflow` only: a schema without a
  descriptor type (or, for WDL, an entry point) renders, but its values get
  the error that the binding is unknown, after they have passed validation.
- **Validation on the host:** the form doesn't validate in the browser; a
  client without a Python backend would validate with a [JavaScript
  validator](../tools/javascript.md) instead.
- **Plain controls:** file references are text fields for a URL or path
  (no DRS or S3 pickers); `time` and `date-time` are text fields; a colour,
  once rendered, always has a value; arrays of strings or numbers are text
  areas with one value per line; arrays of objects, objects without
  `properties`, and unions other than those with a file reference are text
  areas for JSON. The form follows local `$ref`s (`#/...`) only. A slider
  takes `minimum` and `maximum` (not the exclusive bounds) and the step of
  `multipleOf`, counted from `minimum` as browsers do, so its positions
  fail validation if `minimum` isn't a multiple of `multipleOf`.
- **Tests:** the tests cover the host and the logic of the form
  (`form.js`), not the rendering in a browser (`io-schema-form.js`,
  `app.js`), which was checked by hand.
- **Descriptions** with `"x-ga4gh-description-format": "markdown"` are shown
  as plain text, which the guide allows.
- **Error messages:** the host looks for the message in every branch of the
  applicators at the location of a failure, not only in those on its
  evaluation path, and doesn't look through `contains`,
  `unevaluatedProperties` or `unevaluatedItems`. Of the messages at a
  location, it takes the first in a breadth-first search from the
  schemas of the location, which can differ from the outermost on the
  evaluation path (e.g., a message in an `allOf` of the enclosing object
  wins over one behind the property's `$ref`); it doesn't follow
  `$dynamicRef`.
- **Defaults of file references** are prefilled without the checks of
  step 6; the host checks them when the values are sent.
- **Not hardened:** no authentication, no TLS; the host binds to
  `127.0.0.1` by default. It sends a Content Security Policy that allows
  only its own files. It takes values only as JSON (`Content-Type:
  application/json`) and only from its own pages, opened under a loopback
  name (`localhost`, `127.0.0.1`, `::1`) or the address that it binds
  (`Host` and `Origin` headers), so that other web pages can't make it
  submit runs; other requests get `415` or `403`. It answers the reads of
  its API (`GET /api/...`) under those names only, too. This guards against
  browsers only and is no access control: anyone who can reach the host
  can use it, so keep it on a loopback address.
