# WES

## Workflow Execution Service (WES) validation

While a primary goal of the JSON Schema is to enable automated client-side UI generation, it also drastically lowers the barrier for developers building simple, lightweight WES clients or autonomous AI agents, as they may no longer need to parse complex workflow DSLs to construct valid execution requests.

On the backend, WES implementations should adhere to a "trust but verify" security posture. If a WES gateway is aware of an IO Schema for a given workflow (either fetched from TRS or provided dynamically), the server *should* attempt to validate the incoming `workflow_params` JSON payload against it before passing the request to the underlying engine (e.g., Nextflow, Cromwell).

Crucially, if this server-side validation fails, WES APIs must return a deterministic `HTTP 400 Bad Request`. The error response body should explicitly emit the standard JSON Schema validation error path (e.g., `$.inputs.sample_manifest[2].condition: value not in enum`). Furthermore, if the schema author provided an `x-ga4gh-error-message` for the failing property, the WES server should prioritize returning this human-readable instruction (e.g., "Condition must be either control or treatment") over the raw JSON Schema error. This provides human users and AI agents with actionable debugging feedback without having to dig through dense, engine-specific execution logs.

See also [Security considerations](../security.md).

## Guide for WES implementers

> **To be written.** This section will describe, step by step, how a WES
> implementation or gateway validates `workflow_params` against an IO
> schema, and how clients build `workflow_params` from an IO schema (see
> [Converters](../tools/converters.md#from-io-schemas-to-wes)).
