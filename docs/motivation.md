# Motivation

## The usability gap

Tool and workflow registries publish many analytical workflows, but clients that want to run them (portals for people, and AI agents) have no common way to find out what a workflow takes and what it returns. Each workflow language describes its inputs and outputs in its own way, and the GA4GH APIs don't carry an engine-neutral description.

* **Engine-specific interfaces:** Registries such as those implementing the GA4GH Tool Registry Service (TRS) serve the source code of workflows in their own language. Input declarations can be read from that code: CWL declares input types statically ([CWL v1.2, `WorkflowInputParameter`](https://www.commonwl.org/v1.2/Workflow.html#WorkflowInputParameter)), and [cwl-utils](https://github.com/common-workflow-language/cwl-utils) has a `cwl-inputs-schema-gen` command that generates JSON Schema from them; WDL's `parameter_meta` holds structured values ([WDL 1.2, Meta Values](https://github.com/openwdl/wdl/blob/wdl-1.2/SPEC.md#meta-values)); Nextflow pipelines often ship a `nextflow_schema.json` ([nf-schema](https://nextflow-io.github.io/nf-schema/latest/nextflow_schema/nextflow_schema_specification/)); and Galaxy serves JSON Schemas of tool parameters through its API ([galaxyproject/galaxy#23105](https://github.com/galaxyproject/galaxy/pull/23105)). But every client has to support each of these formats separately, and TRS has no engine-neutral contract for inputs and outputs. Portals therefore tend to support only one or a few workflow languages.

* **Opaque outputs:** The `outputs` field of a WES run log is a free-form object ([WES OpenAPI, `RunLog`](https://github.com/ga4gh/workflow-execution-service-schemas/blob/1.1.0/openapi/workflow_execution_service.openapi.yaml)), and WES implementations fill it in different shapes. Clients have no semantic context (e.g., "this URL is a VCF", "this URL is an HTML report") to catalogue the outputs or to show them in a suitable viewer.

* **Tool definitions for agents:** AI agents call tools through JSON Schema definitions of their parameters, e.g., `inputSchema` and `outputSchema` of [MCP tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools). Undocumented or ambiguous workflow parameters lead to invalid run requests and failed runs. A schema for a workflow's inputs and outputs is a starting point for such a tool definition, not a ready-made one: the strict modes of LLM APIs accept only subsets of JSON Schema (see [Portals and clients](adoption/portals.md#ai-agents)).

An engine-neutral description of inputs and outputs, served next to the workflow, closes this gap for clients: they read one format instead of one per workflow language.

## Goals, non-goals, and out of scope

To keep this standard small and focused on interface description, we set the following boundaries.

### Goals

* **Input forms:** Let portals and other clients render input forms, with validation, for registered workflows. Generic JSON Schema form libraries handle the standard keywords; the `x-ga4gh-*` keywords need an adapter (see [Portals and clients](adoption/portals.md)).

* **Requests from agents and other programs:** Give AI agents and other programs a schema from which they can build run requests and check them before submitting. A schema checks the *shape* of a request, not whether the values make sense for the analysis.

* **Semantic output typing:** Standardise the annotation of outputs with viewer hints (e.g., `genome-browser`) and ontology terms, so that portals and data catalogues can interpret the results of a run.

### Non-goals and out of scope (the defenses)

* **No CLI Generation:** We do not attempt to map JSON input values to POSIX bash commands (e.g., mapping `threads: 4` to `-t 4`). The underlying workflow engine or container wrapper is solely responsible for execution binding. Input values still need to be translated into the `workflow_params` of a WES request, whose shape depends on the engine (e.g., CWL `File` objects, WDL names qualified with the workflow name); this translation is specified per engine (see [WES](adoption/wes.md)).

* **No Raw Container Staging (e.g., Bare TES Tasks):** Low-level container execution (such as submitting bare containers via the GA4GH Task Execution Service) is explicitly out of scope. Those APIs require physical data staging instructions (container paths, mount points), whereas this schema defines high-level semantic intents. Standalone tools are supported by this standard *only* when wrapped as modular workflow units (e.g., a CWL `CommandLineTool` or an `nf-core` module) that handle their own staging via a workflow orchestrator.

* **No Hardware Policy Enforcement:** The schema validates the *shape* and *type* of requests (e.g., ensuring `memory_mb` is an integer). Hardware limit bounds-checking (e.g., rejecting requests over 256GB RAM) is explicitly a server-side authorization and deployment policy, not a schema validation task.

See also [Security considerations](security.md).

## The concept: an interface description above workflow languages

The core idea of this proposal is to separate the **interface** of a workflow from its **implementation**.

### Decoupling interface from execution

Languages like CWL, Galaxy XML, and Nextflow represent the *implementation*. They handle the messy realities of data staging, CLI flag compilation, and resource allocation.

The IO Profile is the *public interface*. It describes what a portal or AI agent needs to know to offer the workflow and to build a run request, without the details of the implementation.

### The translation model

This proposal does not seek to replace CWL, WDL, or Nextflow. Instead, it is an **export target**: converters project the inputs and outputs of a workflow, written in its own language, into the profile. Registries such as Dockstore or WorkflowHub, the communities of the workflow languages, or workflow authors can run them when a workflow is published. Clients then read one format, JSON Schema with the profile's keywords, for workflows in any of the supported languages.

See also [Converters](tools/converters.md) and the [adoption path](adoption/index.md#the-adoption-path-ecosystem-independence).
