# Related work

Several standards and tools overlap with this profile. This page says, for each of them, where they overlap, how they differ, and how the profile relates to them: it **adopts** them (uses them as they are), **maps** to them (defines how to translate), **converges** with them (works towards one solution), or **differs** from them (with the reason). The facts were checked against the sources in November 2026.

| Work | Overlap | Relation |
| ----- | ----- | ----- |
| [WES pull request #226](#wes-pull-request-226) | Typed, constrained parameters and structured outputs in WES | Converge |
| [Nextflow pipeline spec (#6900)](#nextflow-pipeline-spec-6900) | Typed inputs and outputs of Nextflow pipelines | Converge |
| [Bioschemas `FormalParameter` and RO-Crate](#bioschemas-formalparameter-and-ro-crate) | Inputs and outputs of workflows, typed with EDAM | Map |
| [MCP tools](#mcp-tools) | JSON Schemas of tool inputs and outputs for AI agents | Map |
| [OGC API Processes](#ogc-api-processes) | JSON Schema per input and output, results keyed by output | Map, differ |
| [cwl-utils `cwl-inputs-schema-gen`](#cwl-utils-cwl-inputs-schema-gen) | JSON Schema from CWL inputs | Adopt |
| [Galaxy tool parameter schemas](#galaxy-tool-parameter-schemas) | JSON Schema of Galaxy tool parameters | Map |
| [bio.tools](#biotools) | EDAM annotations of tool inputs and outputs | Adopt (EDAM), complement |
| [APE and Workflomics](#ape-and-workflomics) | Chaining tools by EDAM annotations | Differ (deferred) |
| [WorkflowHub](#workflowhub) | Registry metadata, TRS, Workflow RO-Crate | Complement |
| [Frictionless Table Schema](#frictionless-table-schema) | Schemas for tabular files | Adopt by reference (deferred) |
| [Croissant](#croissant) | Metadata of machine learning datasets | Differ (out of scope) |

## WES pull request #226

[ga4gh/workflow-execution-service-schemas#226](https://github.com/ga4gh/workflow-execution-service-schemas/pull/226), "Structured parameters and outputs", is an open pull request to WES (last updated on 2026-02-18). It adds an engine-independent way to pass workflow parameters, with types and validation constraints, and a structured format for the outputs of a run.

- **Overlap:** Both describe typed, constrained parameters and structured outputs. Inside GA4GH, the two would compete if both went ahead unchanged.
- **Difference:** WES#226 carries the constraints in each run request. Its reviewers questioned that: constraints "are typically properties of a workflow in the case of a WES" ([comment](https://github.com/ga4gh/workflow-execution-service-schemas/pull/226#discussion_r2389255596)), and defining them per run lets different clients use different constraints for the same workflow ([comment](https://github.com/ga4gh/workflow-execution-service-schemas/pull/226#discussion_r2285599666)). The profile puts them where the reviewers suggested: in a schema that belongs to the workflow and is served with it (e.g., by TRS).
- **Relation: converge.** The profile can be the per-workflow description that WES#226 refers to, instead of a second type system; its outputs model can align with the structured outputs of WES#226. WES#226 is also the venue for a structured error body (see [WES](adoption/wes.md)). We plan to contact its authors.

## Nextflow pipeline spec (#6900)

[nextflow-io/nextflow#6900](https://github.com/nextflow-io/nextflow/pull/6900), "ADR: Pipeline spec", is a draft design record (last updated on 2026-09-22). It proposes a pipeline spec for Nextflow that adopts the nf-core schema (`nextflow_schema.json`) for inputs, adds new properties, including outputs, and can be generated from the pipeline code. A first version of the schema is in [nextflow-io/schemas](https://github.com/nextflow-io/schemas/blob/main/pipeline/v1/schema.json).

- **Overlap:** Typed inputs and outputs of a workflow, as JSON Schema, for Nextflow.
- **Difference:** The pipeline spec is specific to Nextflow; the profile covers several workflow languages and adds keywords for ontology terms and viewers.
- **Relation: converge.** The planned Nextflow converter ([#1](https://github.com/uniqueg/ga4gh-io-schema/issues/1)) reads `nextflow_schema.json`; it should read the pipeline spec once that is stable. Where the pipeline spec and the profile describe the same thing, the profile should use compatible keywords, so that the conversion is lossless. We plan to contact the authors.

## Bioschemas `FormalParameter` and RO-Crate

[Bioschemas `FormalParameter`](https://bioschemas.org/profiles/FormalParameter/1.1-DRAFT) (version 1.1-DRAFT) describes an input or output of a workflow, with a name, a description, EDAM terms for the type of data (`additionalType`) and the format (`encodingFormat`), a default value and whether a value is required. [Workflow RO-Crate](https://w3id.org/workflowhub/workflow-ro-crate/) uses it: parameter definitions, if given, "MUST be provided as `FormalParameter` entities", referenced from the workflow via `input` and `output`. [Workflow Run Crate](https://w3id.org/ro/wfrun/workflow/0.6) records the values of a run as `File` or `PropertyValue` entities, which refer to their `FormalParameter` via `exampleOfWork`. [Five Safes RO-Crate](https://w3id.org/5s-crate/0.4) extends Workflow Run Crate for requests to Trusted Research Environments (TREs).

- **Overlap:** Both describe the inputs and outputs of a workflow and type them with EDAM.
- **Difference:** `FormalParameter` is descriptive metadata (what a parameter is); it has no constraints on values (ranges, patterns, enumerations, nested structure) and isn't used to validate a request. The profile is a validation contract for requests, with the same descriptive core.
- **Relation: map.** An IO schema and the `FormalParameter` entities of a crate are not meant to be maintained side by side: the `FormalParameter` entities can be generated from the IO schema with the mapping below. The values recorded in a Workflow Run Crate can be checked against the IO schema, e.g., before a TRE approves a Five Safes request; such a check confirms the shape of the values, not that the request is safe.

| IO schema (inputs or outputs) | `FormalParameter` |
| ----- | ----- |
| Property name under `inputs` or `outputs` | `name`; the parameter is listed in the workflow's `input` or `output` |
| `title`, `description` | `name` (if no separate identifier is needed), `description` |
| `x-ga4gh-ontology` with an EDAM *data* term | `additionalType` |
| `ontology` of a [file reference](specification/files.md) (e.g., an EDAM *format* term) | `encodingFormat` |
| `mediaType` of a file reference | `encodingFormat` (IANA media type) |
| Listed in `required` | `valueRequired: true` |
| `default` | `defaultValue` |
| `type`, `enum`, `minimum`, `pattern` and other constraints | No equivalent; stays in the IO schema |
| `x-ga4gh-ui-widget`, `x-ga4gh-hidden` and other UI hints | No equivalent; stays in the IO schema |

`FormalParameter` separates the type of data from the format, and so does the profile for files: `x-ga4gh-ontology` names the data, `ontology` of the file reference the format. Schemas written before version 0.3 may have an EDAM format term in `x-ga4gh-ontology`; a converter then decides by the EDAM branch (`data_…` or `format_…`) of the term.

In a Workflow RO-Crate, the IO schema itself can be included as a file of the crate, next to the workflow.

## MCP tools

The [Model Context Protocol (MCP)](https://modelcontextprotocol.io/specification/2025-11-25/server/tools) describes each tool with a required `inputSchema` and an optional `outputSchema` (added in the 2025-06-18 version, with `structuredContent` for results that conform to it). Both are JSON Schemas; since the 2025-11-25 version, they default to JSON Schema 2020-12 if they have no `$schema`.

- **Overlap:** JSON Schemas of a tool's inputs and outputs, the de facto contract for AI agents.
- **Difference:** MCP describes a tool call; the profile describes a workflow, with keywords for files, ontology terms and viewers that MCP clients don't use.
- **Relation: map.** A tool definition can be derived from an IO schema, as described below.

To derive an MCP tool definition from an IO schema:

1. Use the schema under `inputs` as `inputSchema` and the schema under `outputs` as `outputSchema`.
2. Bundle the `$ref`s that the schema uses (under `$defs`); leave no references to remote schemas.
3. Remove the `x-ga4gh-*` keywords, or turn them into text in `description` where they help the model (e.g., the expected file format).
4. For clients that pass the schema to an LLM API in strict mode, reduce the schema to that API's subset (see [AI agents](adoption/portals.md#ai-agents)), and validate the values against the full IO schema before submitting a run.

## OGC API Processes

[OGC API – Processes – Part 1: Core](https://docs.ogc.org/is/18-062r2/18-062r2.html) (OGC 18-062r2) is a web API for running processes. Its process descriptions give each input and output a `schema` member, a JSON Schema fragment (requirements 49 and 53), and its results are "a map using the respective output identifier as the key" (§7.11.4). A [draft Part 2](https://github.com/opengeospatial/ogcapi-processes) adds deploying processes as application packages, including CWL, and [cwl2ogc](https://github.com/eoap/cwl2ogc) converts CWL inputs and outputs into OGC process descriptions.

- **Overlap:** The same model of a JSON Schema per input and output, and outputs keyed by name.
- **Difference:** OGC API – Processes is an execution API, like WES, with the process description built in. The profile is a document that is served by TRS and used with WES, without changing either.
- **Relation: map, differ.** The inputs and outputs of an IO schema map to an OGC process description, property by property. Results keyed by output identifier are what the profile's outputs model needs from WES too.

## cwl-utils `cwl-inputs-schema-gen`

[cwl-utils](https://github.com/common-workflow-language/cwl-utils) has a command, `cwl-inputs-schema-gen`, that "generates a JSON Schema for workflow input parameters from a CWL document".

- **Relation: adopt.** The planned CWL converter ([#21](https://github.com/uniqueg/ga4gh-io-schema/issues/21)) builds on it where possible, and adds outputs, file references and the profile's keywords.

## Galaxy tool parameter schemas

Since [galaxyproject/galaxy#23105](https://github.com/galaxyproject/galaxy/pull/23105) (merged on 2026-07-17), Galaxy serves JSON Schemas of tool parameters through its API (e.g., `GET /api/tools/{tool_id}/parameter_request_schema`), as the Tool Shed does.

- **Difference:** The schemas describe requests to Galaxy's own tool API, with Galaxy's data model (e.g., datasets and collections).
- **Relation: map.** They are a good source for a Galaxy converter, which is not planned for version 0.3.

## bio.tools

[bio.tools](https://bio.tools) registers tools and annotates each *function* of a tool with EDAM terms for its operations and for the type and format of its primary inputs and outputs. Following its [curation guidelines](https://biotools.readthedocs.io/en/latest/curators_guide.html), it doesn't describe individual parameters, and for workflows only the main operations of the workflow as a whole.

- **Overlap:** EDAM annotations of inputs and outputs.
- **Difference:** bio.tools describes what a tool does, at the level of functions; the profile describes the parameters of one workflow, with names, values and constraints.
- **Relation: adopt EDAM, complement.** The profile's `x-ga4gh-ontology` uses the same EDAM terms, so that the two can be compared. A registry can link a workflow's bio.tools entry next to its IO schema; the IO schema doesn't repeat the tool-level description.

## APE and Workflomics

[APE](https://github.com/Workflomics/ape) synthesises candidate workflows from tool annotations in the bio.tools format and an ontology such as EDAM; [Workflomics](https://workflomics.readthedocs.io) uses it to generate and benchmark workflows.

- **Overlap:** Chaining tools by the EDAM types and formats of their inputs and outputs.
- **Relation: differ (deferred).** Chaining workflows by ontology terms is deferred in version 0.3 (see [Roadmap](roadmap.md#deferred)); it needs matching rules (e.g., for more specific terms) that the profile doesn't define. Tools like APE work on tool-level annotations and don't need the profile for that.

## WorkflowHub

[WorkflowHub](https://workflowhub.eu) is a registry of workflows. It uses Workflow RO-Crate as its exchange format ([Workflow RO-Crate](https://about.workflowhub.eu/Workflow-RO-Crate/)), lists inputs and outputs for workflows with a CWL description, and implements TRS 2.0.1 (`https://workflowhub.eu/ga4gh/trs/v2/`).

- **Relation: complement.** WorkflowHub's registry metadata (authors, licence, EDAM topics and operations) describes the workflow; the IO schema describes its interface. WorkflowHub could serve IO schemas as files of a workflow version through TRS and generate the `FormalParameter` entities of its crates from them (see [above](#bioschemas-formalparameter-and-ro-crate)).

## Frictionless Table Schema

[Table Schema](https://datapackage.org/standard/table-schema/) (Data Package v2) describes the columns of tabular data, with field types (e.g., `integer`, `date`, `boolean`) and constraints (e.g., `required`, `unique`, `minimum`, `pattern`, `enum`), and [Table Dialect](https://datapackage.org/standard/table-dialect/) describes delimiters, headers and quoting.

- **Overlap:** The profile's `x-ga4gh-tabular-schema` describes the rows of sample sheets.
- **Relation: adopt by reference (deferred).** Validating tabular files needs the rules that Table Schema and Table Dialect already define (how text cells become typed values, empty cells, dialects). Version 0.3 keeps `x-ga4gh-tabular-schema` as an experimental hint for forms and defers validation of tabular files (see [Roadmap](roadmap.md#deferred)); if it is added, it should reference Table Schema rather than reinvent it.

## Croissant

[Croissant](https://docs.mlcommons.org/croissant/docs/croissant-spec-1.1.html) (MLCommons, version 1.1) describes machine learning datasets, based on schema.org, with record sets and fields.

- **Relation: differ (out of scope).** Croissant describes datasets, not the inputs and outputs of workflows. Whether the profile should cover machine learning pipelines, and how it would relate to Croissant, is an [open question](roadmap.md#open-questions).
