# Adoption

The profile is independent of workflow engines. Its integration with the GA4GH APIs for federated analysis (TRS, WES, DRS) lets platforms that implement them offer workflows of several languages through one interface.

* [TRS](trs.md): serving IO schemas from tool registries.
* [WES](wes.md): validating run requests against IO schemas.
* [Portals and clients](portals.md): rendering forms, resolving DRS
  identifiers and interpreting outputs.

## The end-to-end GA4GH lifecycle (summary)

With IO schemas served by TRS and used by clients and WES, a run goes through the following steps, without the client having to know the workflow's language:

1. **Discovery (TRS):** A generic client or AI agent fetches a workflow and its IO schema, a file of the workflow's TRS entry (see [TRS](trs.md)).

2. **Configuration (Client/UI):** The client renders an input form from the schema, with a JSON Schema form library and an adapter for the `x-ga4gh-*` keywords (see [Portals and clients](portals.md)).

3. **Data Access (DRS):** The schemes of the schema's [file references](../specification/files.md) let the client offer a DRS picker for inputs that accept `drs`. The client submits the `drs://` identifiers; the execution side resolves them with the user's delegated credentials when it stages the data (see [Access to data](../security.md#access-to-data)).

4. **Execution (WES):** The client checks the input values against the schema, translates them into the `workflow_params` of the workflow's engine and submits the run. A WES server that knows the schema can check the request again and reject it with an error that names the failing parameter, using `x-ga4gh-error-message` where the schema provides one (see [WES](wes.md)).

5. **Result Interpretation:** WES returns the locations of the outputs, and the client matches them with the schema's outputs to choose viewers (tables, sandboxed HTML, or download) and to read their ontology terms.

## The adoption path (ecosystem independence)

The success of this profile does not rely on modifying the core CWL, WDL, or Nextflow language specifications. Adoption can be driven organically through multiple avenues across the ecosystem:

* **Platform Auto-Generation:** Registries like Dockstore or WorkflowHub can implement server-side parsers that automatically extract and generate this JSON Schema from existing `Schema Salad` (CWL) or `nextflow_schema.json` files during workflow ingestion, publishing them as files of the workflow's TRS entry.

* **Sidecar Files:** For WDL workflows or legacy pipelines, authors can manually bundle the `.schema.json` file as an associated file in their TRS submission.

See also [Converters](../tools/converters.md).
