# Adoption

While the schema is inherently domain and orchestrator-agnostic, formalizing its integration within the GA4GH Federated Analysis API ecosystem provides an immediate, massive capability upgrade for existing compliant platforms.

* [TRS](trs.md): serving IO schemas from tool registries.
* [WES](wes.md): validating run requests against IO schemas.
* [Portals and clients](portals.md): rendering forms, resolving DRS
  identifiers and interpreting outputs.

## The end-to-end GA4GH lifecycle (summary)

By adopting this IO Schema across the GA4GH API portfolio, the ecosystem gains a cohesive, end-to-end execution lifecycle that completely decouples front-end clients from back-end engine implementations:

1. **Discovery (TRS):** A generic client or AI agent fetches a workflow and its abstract `IO_SCHEMA`.

2. **Configuration (Client/UI):** The client automatically renders a type-safe form using off-the-shelf industry tools.

3. **Data Access (DRS):** The schema's `x-ga4gh-drs-uri` flags prompt the client to securely resolve data identifiers and tokens.

4. **Execution (WES):** The client constructs a deterministically valid JSON payload and submits it. The WES gateway performs final server-side validation against the schema, executing the job safely or returning immediate, actionable debugging context via `x-ga4gh-error-message`.

5. **Result Interpretation:** WES returns physical output URIs, and the client cross-references the schema to instantly apply UI visualization hints or semantic ontology tags for downstream chaining.

## The adoption path (ecosystem independence)

The success of this profile does not rely on modifying the core CWL, WDL, or Nextflow language specifications. Adoption can be driven organically through multiple avenues across the ecosystem:

* **Platform Auto-Generation:** Registries like Dockstore or WorkflowHub can implement server-side parsers that automatically extract and generate this JSON Schema from existing `Schema Salad` (CWL) or `nextflow_schema.json` files during workflow ingestion, projecting them as `IO_SCHEMA` file types automatically.

* **Sidecar Files:** For WDL workflows or legacy pipelines, authors can manually bundle the `.schema.json` file as an associated file in their TRS submission.

* **Agent-Driven Authoring:** If a schema is missing, human users or AI agents can draft the JSON Schema themselves for a workflow they wish to run. While this represents a one-time upfront effort, the resulting schema provides a permanent, reusable contract for all future runs across all compliant orchestrators.

See also [Converters](../tools/converters.md).
