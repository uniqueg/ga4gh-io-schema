# WES

Requirements on this page use the key words of BCP 14, as described in
[Notational conventions](../specification/conformance.md#notational-conventions).

## Workflow Execution Service (WES) validation

Besides input forms, an IO schema helps developers of WES clients and AI agents: they can check run requests against one schema format instead of reading each workflow language.

On the backend, WES implementations follow a "trust but verify" security posture. Validation on the server is OPTIONAL (see the conformance class [WES server](../specification/conformance.md#wes-server)), and RECOMMENDED where a schema is available: if a WES gateway has an IO Schema for a given workflow from a trusted source (the workflow's TRS entry or a schema bundled with the deployment; never one supplied in the run request, see [Sources of schemas](../security.md#sources-of-schemas)), the server SHOULD validate the incoming `workflow_params` JSON payload against it before passing the request to the underlying engine (e.g., Nextflow, Cromwell). A server that validates MUST meet the requirements for servers in [Security considerations](../security.md).

An IO schema describes input *values* (the `inputs` part of the schema); WES receives `workflow_params`, whose shape depends on the engine (e.g., WDL names qualified with the workflow name, CWL `File` objects). A server therefore translates `workflow_params` back into input values with the engine's binding (the entry point and parameter bindings of the schema, see [Identity and engine binding](../specification/identity.md)) before it validates them, and reports errors in terms of `workflow_params`, which is what the client sent.

If this server-side validation fails, the server MUST return `HTTP 400 Bad Request` with the error body of WES 1.1, [`ErrorResponse`](https://github.com/ga4gh/workflow-execution-service-schemas/blob/1.1.0/openapi/workflow_execution_service.openapi.yaml), which has only the fields `msg` and `status_code`. The message names the failing parameter with a [JSON Pointer](https://www.rfc-editor.org/rfc/rfc6901) relative to `workflow_params`, the form in which JSON Schema 2020-12 reports instance locations ([JSON Schema Core, §12.3.3](https://json-schema.org/draft/2020-12/json-schema-core#section-12.3.3)). If the schema author provided an `x-ga4gh-error-message` that covers the failure, the server returns it after the pointer, in place of the validator's message ([Error messages](../specification/keywords.md#error-messages) defines which message covers which failure, with more examples); otherwise, it builds the message from the pointer and the keyword that failed (e.g., `enum`), not from the validator's default text, which often repeats the value (see [Error messages and logs](../security.md#error-messages-and-logs)). For example, a request with `"workflow_params": {"condition": "contrl"}`, where `condition` must be `control` or `treatment`, gets:

```json
{
  "msg": "/condition: Condition must be either control or treatment",
  "status_code": 400
}
```

Validation covers the request itself. Contents of files referenced by the request, such as the rows of a sample sheet, are not part of `workflow_params`; checking them means reading the files on the server (see [Security considerations](../security.md)).

WES 1.1 has no structured error body (e.g., a list of errors, each with a pointer and a message). Such a body would need a change to WES; the venue for proposing it is the open pull request on structured parameters and outputs, [ga4gh/workflow-execution-service-schemas#226](https://github.com/ga4gh/workflow-execution-service-schemas/pull/226).

See also [Security considerations](../security.md).

## Outputs of runs

WES servers report the outputs of a run in `RunLog.outputs`, a free-form
object whose shape depends on the engine and the server. Clients and
gateways turn it into the *normalised outputs object* of the run, keyed by
the outputs of the IO schema, as defined in
[Outputs](../specification/outputs.md#the-normalised-outputs-object). For
engines that don't report outputs by name, this needs the server to list the
files of the run, relative to its output directory (see
[`x-ga4gh-output-glob`](../specification/outputs.md#x-ga4gh-output-glob)).

## Guide for WES implementers

Version 0.3 of the profile needs no change of WES: clients send ordinary
WES 1.1 run requests, and servers that validate them use only what WES and
TRS already provide.

### Building run requests (clients)

1. Find the IO schema of the workflow in TRS and check it, as described in
   [Discovery by clients](trs.md#discovery-by-clients) (file type
   `IO_SCHEMA`, or `OTHER` at the path `ga4gh-io.schema.json`; `$schema`,
   `x-ga4gh-workflow`, drift).
2. Collect the input values, e.g., with a form rendered from the schema
   (see [Portals and clients](portals.md)).
3. Validate the values against `inputs`, check every file reference value
   against the deployment's allow-list, and translate the values into
   `workflow_params` with the binding of the schema's descriptor type (see
   [Engine bindings](../specification/engine-bindings.md)).
4. Set `workflow_type`, `workflow_type_version` and `workflow_url` from the
   schema and TRS (see [Run requests](../specification/engine-bindings.md#run-requests)),
   and submit the request (`POST /runs`).

The [`wes-params`](../tools/wes-params.md) tool does steps 3 and 4 (except
the submission).

### Can the WES fetch the workflow?

A run request with a TRS URL in `workflow_url` is only runnable if the WES
server fetches that URL. WES 1.1 leaves this to the deployment: it
defines `workflow_url` as the URL of the workflow document (or a relative
path to an attached file), not which URLs a server must fetch, so a server
may refuse or fail on URLs that it can't or won't fetch. Before it sends such a request, a client
needs to know two things about the WES:

- **TRS URL support:** whether the server fetches a remote `workflow_url`
  over `http(s)` at all, and, for multi-file workflows, also the files that
  the primary descriptor imports, relative to that URL (see [Workflow URLs in
  TRS](../specification/engine-bindings.md#workflow-urls-in-trs)). Some
  servers take only workflows attached to the request
  (`workflow_attachment`), or only workflows from a list of their own.
- **Reachable hosts:** whether the server can reach the host of the TRS,
  and is allowed to. A TRS inside a private network (e.g., a stack of
  containers, where the TRS has a name that only resolves inside it), a
  firewall or egress policy of the WES, or an allow-list of hosts that
  the server fetches workflows from can each make the URL unreachable
  from the server, even if the client reaches it. A TRS that needs
  authorisation is unreachable too, unless the deployment gives the
  server its own credentials for it: the server doesn't get the user's.

The WES API doesn't tell a client either of them. Its `service-info` lists
the `workflow_type_versions` and the `supported_filesystem_protocols`, but
doesn't say whether these protocols apply to `workflow_url`, and no field
names the TRS hosts that the server reaches. Until it does
(see [Open questions](../roadmap.md#open-questions)), deployments can tell
clients in these ways:

- **Configuration of the client:** the portal or gateway that builds run
  requests is configured with the WES servers it submits to and, for each,
  whether it takes TRS URLs and from which TRS base URLs (e.g., a WES and
  the TRS of the same deployment). This is the most reliable way today,
  because the deployment knows both sides.
- **Service registry:** a deployment that registers its services in a
  GA4GH Service Registry can describe the pairing in the WES entry: its
  `description` and `documentationUrl` for people. For machines, a
  deployment can add, as its own convention, an entry to the `tags` of the
  WES `service-info` (a map of strings), e.g.,
  `"trs_urls": "https://trs.example.org/ga4gh/trs/v2"`. Such tags are not
  standardised: a generic client can't rely on them, and SHOULD treat a
  missing tag as "unknown", not as "no".
- **Trying:** a client MAY submit the request and handle the failure. A
  server that can't fetch the `workflow_url` may only fail the run later
  (state `SYSTEM_ERROR` or `EXECUTOR_ERROR`), not reject the request, so
  the client SHOULD tell its user that the run may fail for this reason.

Where a WES can't fetch from the TRS, the client can fetch the files
itself and attach them: it downloads the primary descriptor and the files
it imports (`GET .../{type}/files` lists them) as `workflow_attachment`,
under their paths, and sets `workflow_url` to the relative path of the
primary descriptor (e.g., `workflows/variant_calling.wdl`). The [form proof
of concept](form.md) sets such a `workflow_url` when it knows no TRS URL,
but attaches no files. With attachments, the
server runs the files as sent; a server that validates requests still gets
the IO schema from a trusted source, not from the attachments (see
[Sources of schemas](../security.md#sources-of-schemas)).

### Validating run requests (servers)

1. Get the IO schema of the workflow from a trusted source (the TRS entry
   that `workflow_url` points to, or a schema bundled with the deployment);
   never from the request. Reject requests for workflows whose schema has
   references that can't be resolved locally.
2. Check the size and depth of `workflow_params` against the limits of the
   deployment (see [Regular expressions and size
   limits](../security.md#regular-expressions-and-size-limits)).
3. Translate `workflow_params` back into input values with the binding of
   the request's `workflow_type` (see [From `workflow_params` back to input
   values](../specification/engine-bindings.md#from-workflow_params-back-to-input-values)).
4. Validate the values against `inputs`, and check every file reference
   value (see [URIs and file
   references](../security.md#uris-and-file-references)).
5. On failure, reject the request with `HTTP 400 Bad Request` and an
   `ErrorResponse` whose `msg` names the JSON Pointer into `workflow_params`
   and the rule that failed (see above); otherwise, pass the request on to
   the engine.

The [`wes-validate`](../tools/wes-validate.md) tool, and its Python API,
do steps 3 to 5 (except the HTTP response, whose body it builds).
