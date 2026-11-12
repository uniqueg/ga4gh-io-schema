# WES

## Workflow Execution Service (WES) validation

Besides input forms, an IO schema helps developers of WES clients and AI agents: they can check run requests against one schema format instead of reading each workflow language.

On the backend, WES implementations should adhere to a "trust but verify" security posture. If a WES gateway has an IO Schema for a given workflow from a trusted source (the workflow's TRS entry or a schema bundled with the deployment; never one supplied in the run request, see [Sources of schemas](../security.md#sources-of-schemas)), the server *should* attempt to validate the incoming `workflow_params` JSON payload against it before passing the request to the underlying engine (e.g., Nextflow, Cromwell). A server that validates MUST meet the requirements for servers in [Security considerations](../security.md).

An IO schema describes input *values* (the `inputs` part of the schema); WES receives `workflow_params`, whose shape depends on the engine (e.g., WDL names qualified with the workflow name, CWL `File` objects). A server therefore translates `workflow_params` back into input values with the engine's binding before it validates them, and reports errors in terms of `workflow_params`, which is what the client sent.

If this server-side validation fails, the server returns `HTTP 400 Bad Request` with the error body of WES 1.1, [`ErrorResponse`](https://github.com/ga4gh/workflow-execution-service-schemas/blob/1.1.0/openapi/workflow_execution_service.openapi.yaml), which has only the fields `msg` and `status_code`. The message names the failing parameter with a [JSON Pointer](https://www.rfc-editor.org/rfc/rfc6901) relative to `workflow_params`, the form in which JSON Schema 2020-12 reports instance locations ([JSON Schema Core, §12.3.3](https://json-schema.org/draft/2020-12/json-schema-core#section-12.3.3)). If the schema author provided an `x-ga4gh-error-message` for the failing property, the server returns it; otherwise, it builds the message from the pointer and the keyword that failed (e.g., `enum`), not from the validator's default text, which often repeats the value (see [Error messages and logs](../security.md#error-messages-and-logs)). For example, a request with `"workflow_params": {"condition": "contrl"}`, where `condition` must be `control` or `treatment`, gets:

```json
{
  "msg": "/condition: Condition must be either control or treatment",
  "status_code": 400
}
```

Validation covers the request itself. Contents of files referenced by the request, such as the rows of a sample sheet, are not part of `workflow_params`; checking them means reading the files on the server (see [Security considerations](../security.md)).

WES 1.1 has no structured error body (e.g., a list of errors, each with a pointer and a message). Such a body would need a change to WES; the venue for proposing it is the open pull request on structured parameters and outputs, [ga4gh/workflow-execution-service-schemas#226](https://github.com/ga4gh/workflow-execution-service-schemas/pull/226).

See also [Security considerations](../security.md).

## Guide for WES implementers

> **To be written.** This section will describe, step by step, how a WES
> implementation or gateway validates `workflow_params` against an IO
> schema, and how clients build `workflow_params` from an IO schema (see
> [Converters](../tools/converters.md#from-io-schemas-to-wes)).
