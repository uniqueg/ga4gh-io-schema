# GA4GH IO Schema Profile: Proposal for Universal Workflow and Component Interfaces

## 1. Versioning Matrix

| Version | Date | Author | Notes |
| ----- | ----- | ----- | ----- |
| **v0.1** | 2026-10-10 | Alexander Kanitz | Initial Draft: Ecosystem survey, evaluation, and GA4GH JSON Schema Profile proposal. |
| **v0.2** | 2026-10-13 | Alexander Kanitz | Major rewrite addressing architectural reviews. Reframed standard as a universal Interface Definition Language (IDL). Explicitly scoped out bare TES execution. Clarified tabular data sovereignty. Mapped custom properties to `nf-schema`. Expanded GA4GH API lifecycle and RO-Crate Profiles integration. |

## 2. Executive Summary

This document proposes the creation of a **JSON Schema Profile**—an Interface Definition Language (IDL) acting as the "OpenAPI specification" for computational workflows and modular analytical components.

Currently, computational tasks are tightly coupled to their underlying execution engines (e.g., Nextflow, CWL, WDL). This profile establishes a strict, machine-readable contract for inputs and outputs that sits *above* these execution languages. By defining the public presentation of a workload rather than its execution mechanics, this standard enables any generic web portal to automatically generate UI forms, allows metadata catalogs to seamlessly understand outputs, and provides AI agents with the deterministic schemas required for workflow composition.

While this standard seamlessly integrates with the GA4GH Federated Analysis ecosystem (TRS, WES, DRS) as a primary benefactor, it is fundamentally **domain-agnostic** and engine-independent, capable of describing generic ETL jobs or machine learning pipelines just as effectively as genomic aligners.

## 3. Motivation: The Usability Gap

Modern computational science relies on a massive, distributed catalog of analytical tools. However, regardless of the scientific domain, a critical "usability gap" exists between static registries (where tools are published) and dynamic clients (human UIs or AI agents that want to run them) due to a lack of universally understood I/O definitions.

* **Opaque Interfaces:** Registries currently serve engine-specific source code. Generic web portals and AI agents cannot safely or reliably parse Nextflow Groovy configurations, WDL `parameter_meta` blocks, or CWL JavaScript expressions to understand what a workload requires. This forces portals into becoming "walled gardens" that only support single workflow languages.

* **The "Black Box" Outputs:** Workflows generate files, but execution engines typically return unstructured lists of URLs or raw directories in their logs. Clients have no semantic context (e.g., "this URL is a VCF", "this URL is an HTML report") to know how to catalog the outputs or automatically render them in interactive visualization widgets.

* **Agentic Friction:** AI agents rely on well-defined JSON schemas to confidently prepare valid API calls. Ambiguous or undocumented parameters lead to hallucinations, failed compute jobs, and broken workflow chaining.

Solving this gap generically unlocks immediate operational benefits for any compute orchestrator. By defining a universal IDL, we turn static registries into fully executable, UI-ready, and AI-navigable catalogs.

## 4. Goals, Non-Goals, and Out of Scope

To ensure this standard remains lightweight, universally adoptable, and strictly focused on interface definition, we establish the following boundaries.

### 4.1 Goals

* **Automated UI Generation:** Enable any generic client or platform to automatically render intuitive, strictly validated input forms for any registered workload using off-the-shelf industry tooling.

* **AI & Machine Interoperability:** Provide a deterministic format that AI agents can natively ingest to construct valid run requests and intelligently chain outputs to downstream inputs.

* **Semantic Output Typing:** Standardize the annotation of output files with visualization hints (e.g., `genome-browser`) and ontology terms, allowing UIs and data catalogs to automatically contextualize execution results.

### 4.2 Non-Goals and Out of Scope (The Defenses)

* **No CLI Generation:** We do not attempt to map JSON input values to POSIX bash commands (e.g., mapping `threads: 4` to `-t 4`). The underlying workflow engine or container wrapper is solely responsible for execution binding.

* **No Raw Container Staging (e.g., Bare TES Tasks):** Low-level container execution (such as submitting bare containers via the GA4GH Task Execution Service) is explicitly out of scope. Those APIs require physical data staging instructions (container paths, mount points), whereas this schema defines high-level semantic intents. Standalone tools are supported by this standard *only* when wrapped as modular workflow units (e.g., a CWL `CommandLineTool` or an `nf-core` module) that handle their own staging via a workflow orchestrator.

* **No Hardware Policy Enforcement:** The schema validates the *shape* and *type* of requests (e.g., ensuring `memory_mb` is an integer). Hardware limit bounds-checking (e.g., rejecting requests over 256GB RAM) is explicitly a server-side authorization and deployment policy, not a schema validation task.

## 5. The Concept: A Universal Compute IDL

The core philosophy of this proposal is the strict separation of **Interface** from **Implementation**.

### 5.1 Domain Agnosticism

Computational orchestration is not unique to genomics. Modern bioinformatics is heavily intertwined with Data Science and Machine Learning. Because this profile relies on native JSON Schema, it is perfectly suited to describe the hyperparameter spaces (learning rates, batch sizes, categorical enums) of PyTorch training pipelines or distributed database ETL jobs. The standard treats all computational units as agnostic mathematical functions: they take typed inputs and produce typed outputs.

### 5.2 Decoupling Interface from Execution

Languages like CWL, Galaxy XML, and Nextflow represent the *implementation*. They handle the messy realities of data staging, CLI flag compilation, and resource allocation.

The IO Profile is the *public presentation*. It provides the semantic contract that a UI or AI agent needs to understand the tool, completely isolating the client from the implementation details.

### 5.3 The Translation Model

This proposal does not seek to replace CWL, WDL, or Nextflow. Instead, it acts as the universal **export target**. Platforms like Dockstore or WorkflowHub, or the workflow engine communities themselves, can project their complex, engine-specific definitions into this standardized format upon publication. External clients then only have to learn one parser—JSON Schema—to interact with the entire global catalog of computational tools.

## 6. Ecosystem Survey & The "15th Standard" Dilemma

We surveyed existing input and output descriptor solutions across prominent computational workflow languages and data packaging standards to determine if an existing format could serve as a universal IDL.

### 6.1 Input Schema Landscape

| Ecosystem / Standard | Primary Schema Standard | Ecosystem Coupling | UI Generation Capable | Complex Data (Sample Tables) |
| ----- | ----- | ----- | ----- | ----- |
| **Nextflow** | JSON Schema (`nf-schema`) | Low | High | High (via CSV validation rules) |
| **CWL** | Schema Salad (Avro/JSON-LD) | High | Medium | Typed Nested Records |
| **WDL** | `parameter_meta` (Custom) | Medium | Platform-specific | Opaque Files |
| **Snakemake** | JSON Schema & PEP | Low | Medium | High (Native PEP Support) |
| **Galaxy** | Tool XML | Very High | Very High | Collections (Paired/List) |

### 6.2 Output Schema Landscape

| Ecosystem / Standard | Output Definition Strength | Semantic Ontology Support | UI Visualization Hints | Tabular Schema Integration |
| ----- | ----- | ----- | ----- | ----- |
| **Nextflow** | Low (Directory structures)\* | None Natively | External (MultiQC) | Manual |
| **CWL** | High (Strict typing) | High (EDAM native) | None | Manual |
| **WDL** | Medium (Typed primitives) | Custom (`parameter_meta`) | Platform Dependent | Manual |
| **Snakemake** | Low (File patterns) | None Natively | External | Manual |
| **Galaxy** | Very High (Tool XML) | High (Internal Datatypes) | High (Display Apps) | Medium |

*(Note: The Nextflow community recognizes this gap and is actively working to standardize output schemas via initiatives like PR #6900 `nextflow_spec.json`).*

### 6.3 Why Not Adopt an Existing Solution?

The survey reveals a stark divide. We can rule out several ecosystems immediately for the purposes of a universal IDL:

* **CWL & Galaxy:** Highly robust, but inextricably coupled to their execution engines. Parsing CWL's Schema Salad or Galaxy's Tool XML in a generic React web app requires evaluating JavaScript or Python macros, which is unsafe and highly complex.

* **WDL:** Relies on the `parameter_meta` block, which is effectively free-text and lacks a standardized, parsable schema rule set.

**The "JSON Schema Adapter" Dilemma:**
Nextflow (`nf-schema`) and Snakemake already use JSON Schema for input validation. A valid question is: *Why not just adopt `nf-schema` as the universal standard?*

While `nf-schema` is a massive inspiration for this proposal, it falls short of being a universal IDL for three critical reasons:

1. **Cloud-Toxic Directives:** `nf-schema` includes custom keywords like `exists`, which instructs the engine to verify a file exists on the local filesystem before running. In a distributed cloud environment where files are referenced by `s3://` or `drs://` URIs, a web client cannot possibly perform this check without violating the cloud data perimeter.

2. **Weak Output Contracts:** Output definitions in these ecosystems have historically been weak, relying on unstructured directory globs rather than strict, semantically typed key-value pairs.

3. **Missing UI/Semantic Vocabulary:** Existing schemas lack the standardized UI widget hints and ontology bindings necessary for generic portals to render interfaces outside of their native ecosystems.

Therefore, we propose adopting **pure JSON Schema (Draft 2020-12)** as our foundation, stripped of any engine-specific execution directives, and extended with a targeted set of custom `x-ga4gh-*` annotations to support domain-specific semantics and UI rendering.

## 7. Input Architecture & The Extension Vocabulary

To maintain maximum compatibility with existing libraries (e.g., UI form generators, LLMs), the profile strictly relies on JSON Schema Draft 2020-12.

### 7.1 Leveraging Native JSON Schema (What We Don't Reinvent)

Where workflow languages have historically invented proprietary keywords, this profile dictates the use of native JSON Schema features:

* **File Paths and References:** Instead of proprietary file types, developers must use the native string formats: `{"type": "string", "format": "uri"}`.

* **Mimetypes:** Instead of custom `mimetype` properties, developers must use the native `contentMediaType` keyword.

* **Uniqueness:** Instead of custom `uniqueEntries` flags for arrays, developers must use the native `uniqueItems: true`.

### 7.2 Tabular Data & Cloud Sovereignty

Workflows heavily rely on tabular data (e.g., CSV sample sheets). Validating these files before a run prevents time-wasting and potentially expensive pipeline failures. To facilitate this, the profile introduces `x-ga4gh-tabular-schema`—a nested JSON array definition that describes the internal row/column structure of a CSV/TSV file.

Per the JSON Schema specification, standard client libraries ignore `x-` annotations because they are unrecognized extension keywords. To actively validate a CSV against this schema, a platform must implement a custom parser.

Here, we must clearly delineate client-side versus server-side boundaries to preserve cloud data sovereignty. Forcing a generic web UI to download a massive, potentially sensitive patient sample sheet (e.g., fetched via a DRS URI) directly into the user's browser just to run client-side validation violates the data perimeter. Instead, UIs can use the `x-ga4gh-tabular-schema` as a *hint* to auto-generate an interactive spreadsheet grid for the user to fill out *before* saving it to the cloud. Meanwhile, the orchestrator or API gateway, sitting safely behind the firewall, can use a custom parser to securely validate the physical file prior to launching the compute.

### 7.3 The `x-ga4gh-*` Vocabulary

We propose the following initial set of custom annotations to support execution semantics and dynamic UIs. Where applicable, we explicitly map these to their conceptual origins in the Nextflow ecosystem (`nf-schema`) to acknowledge prior art and ease adoption.

* `x-ga4gh-drs-uri` *(boolean)*: Indicates if a string URI is expected to be a valid Data Repository Service (DRS) identifier. While the `drs://` URI scheme often makes this explicit at runtime, this flag allows UIs to proactively render a DRS-specific data browser or resolution widget before a user provides input.

* `x-ga4gh-ontology` *(string, uri)*: Maps an input or output to a formal ontology term (e.g., `http://edamontology.org/format_1929`), enabling semantic linking and automated reasoning.

* `x-ga4gh-ui-widget` *(string)*: A hint for web portals to render a specific component. *Relation to nf-schema: Equivalent in intent to `nf-schema`'s UI rendering hints (e.g., `widget_type` as used in nf-core web interfaces), but this profile mandates referencing a standardized GA4GH vocabulary (e.g., `slider`, `genome-browser`) rather than ecosystem-specific strings.*

* `x-ga4gh-tabular-schema` *(object)*: A nested JSON schema dictating the expected array/object structure of an opaque tabular file. *Relation to nf-schema: Functionally equivalent to `nf-schema`'s ability to apply a schema to a samplesheet. We explicitly namespace it as `x-ga4gh-tabular-schema` to prevent standard JSON Schema validators from confusing it with standard object `properties` or the `$schema` keyword.*

* `x-ga4gh-fa-icon` *(string)*: FontAwesome icon class to display next to the parameter in dynamic UIs. *Relation to nf-schema: Equivalent to the `fa_icon` property.*

* `x-ga4gh-description-format` *(string)*: Indicates the formatting of the standard `description` field (accepted values: `plain_text` (default), `markdown`, `rst`). *Relation to nf-schema: Equivalent in intent to the `help_text` property, but relies on formatting the standard JSON Schema `description` field rather than creating a secondary text property.*

* `x-ga4gh-hidden` *(boolean)*: Signals UI generators to hide this parameter under "Advanced" toggles. *Relation to nf-schema: Equivalent to the `hidden` property.*

* `x-ga4gh-error-message` *(string)*: A custom, human-readable error message to display if payload validation fails. *Relation to nf-schema: Equivalent to the `errorMessage` property.*

## 8. The Output Contract

Outputs are traditionally the most opaque part of pipeline execution. The IO Profile solves this by establishing a **Key-Matching Contract** that separates semantic instructions from physical data retrieval.

### 8.1 The Key-Matching Mechanism

An AI agent or UI client does not need to know which internal `/scratch` folder an engine used, nor does it need to scan an output directory guessing which file is the alignment BAM. The contract works via a simple JSON key intersection:

1. **The Schema (The "What"):** The IO Profile defines the semantic intent of an output key.
   *(e.g., `"alignment_track": { "x-ga4gh-ui-widget": "genome-browser" }`)*

2. **The Execution Log (The "Where"):** When the engine finishes (e.g., via a WES `RunLog`), the server responds with the physical location of that same key.
   *(e.g., `"outputs": { "alignment_track": "s3://bucket/results/sample.bam" }`)*

3. **The Client (The Merge):** The UI or Agent cross-references the keys. It now possesses the file's physical URL *and* the instruction to load it directly into an interactive genome browser component.

### 8.2 Agentic Chaining

This explicit input and output contract is what makes the ecosystem truly "Agent-Ready." Because one workload's output is another workload's input, an AI tasked with chaining workflows together relies on the `x-ga4gh-ontology` terms mapped across both sides of the contract. If Workflow A produces an output tagged as an EDAM VCF format, the agent deterministically knows it can route that URL directly into Workflow B's input that demands a VCF format, without ever downloading or inspecting the file.

## 9. Schema Examples

The following examples demonstrate the schema in practice, utilizing the GA4GH IO Profile Meta-Schema to ensure compliance.

### 9.1 Example 1: Full Workflow with Tabular Validation

This example demonstrates how to validate a workflow that takes a CSV sample sheet as input.

> *The full schema defining the workflow inputs and outputs is available at [`../tests/data/workflow.schema.json`](../tests/data/workflow.schema.json).*

### 9.2 Example 2: Single-Step Workflow Component

This standard works equally well for defining modular, single-step units (such as a CWL `CommandLineTool` or an `nf-core` module) executed via a workflow orchestrator.

> *The full schema defining the modular component is available at [`../tests/data/tool.schema.json`](../tests/data/tool.schema.json).*

## 10. GA4GH Ecosystem Integration

While the schema is inherently domain and orchestrator-agnostic, formalizing its integration within the GA4GH Federated Analysis API ecosystem provides an immediate, massive capability upgrade for existing compliant platforms.

### 10.1 Tool Registry Service (TRS) Integration

To allow clients to discover these schemas natively, we recommend extending the TRS specification to formally recognize schemas as primary artifacts.

Specifically, TRS should introduce a new enum value for the `ToolFile` `file_type`, such as `IO_SCHEMA`. To ensure TRS remains agnostic and does not artificially lock out other ecosystem schemas, this file type should be accompanied by metadata or an annotation pointing to a standardized vocabulary of schema types (e.g., `ga4gh-io-schema`, `nf-schema`). This distinct file type allows generic clients (or AI agents) to pull the lightweight JSON contract independently from downloading the heavier, engine-specific source code.

### 10.2 Workflow Execution Service (WES) Validation

While a primary goal of the JSON Schema is to enable automated client-side UI generation, it also drastically lowers the barrier for developers building simple, lightweight WES clients or autonomous AI agents, as they may no longer need to parse complex workflow DSLs to construct valid execution requests.

On the backend, WES implementations should adhere to a "trust but verify" security posture. If a WES gateway is aware of an IO Schema for a given workflow (either fetched from TRS or provided dynamically), the server *should* attempt to validate the incoming `workflow_params` JSON payload against it before passing the request to the underlying engine (e.g., Nextflow, Cromwell).

Crucially, if this server-side validation fails, WES APIs must return a deterministic `HTTP 400 Bad Request`. The error response body should explicitly emit the standard JSON Schema validation error path (e.g., `$.inputs.sample_manifest[2].condition: value not in enum`). Furthermore, if the schema author provided an `x-ga4gh-error-message` for the failing property, the WES server should prioritize returning this human-readable instruction (e.g., "Condition must be either control or treatment") over the raw JSON Schema error. This provides human users and AI agents with actionable debugging feedback without having to dig through dense, engine-specific execution logs.

### 10.3 Data Repository Service (DRS) Interplay

The `x-ga4gh-drs-uri` flag acts as a critical bridge between the UI and the data access layer. By tagging an input string with this annotation, a WES client is proactively signaled to spawn a DRS resolution or authorization widget *before* submitting the compute request, guaranteeing that the WES runner receives actionable data locators rather than unresolved, potentially inaccessible identifiers.

### 10.4 The End-to-End GA4GH Lifecycle (Summary)

By adopting this IO Schema across the GA4GH API portfolio, the ecosystem gains a cohesive, end-to-end execution lifecycle that completely decouples front-end clients from back-end engine implementations:

1. **Discovery (TRS):** A generic client or AI agent fetches a workflow and its abstract `IO_SCHEMA`.

2. **Configuration (Client/UI):** The client automatically renders a type-safe form using off-the-shelf industry tools.

3. **Data Access (DRS):** The schema's `x-ga4gh-drs-uri` flags prompt the client to securely resolve data identifiers and tokens.

4. **Execution (WES):** The client constructs a deterministically valid JSON payload and submits it. The WES gateway performs final server-side validation against the schema, executing the job safely or returning immediate, actionable debugging context via `x-ga4gh-error-message`.

5. **Result Interpretation:** WES returns physical output URIs, and the client cross-references the schema to instantly apply UI visualization hints or semantic ontology tags for downstream chaining.

## 11. Discussion

### 11.1 The Adoption Path (Ecosystem Independence)

The success of this profile does not rely on modifying the core CWL, WDL, or Nextflow language specifications. Adoption can be driven organically through multiple avenues across the ecosystem:

* **Platform Auto-Generation:** Registries like Dockstore or WorkflowHub can implement server-side parsers that automatically extract and generate this JSON Schema from existing `Schema Salad` (CWL) or `nextflow_schema.json` files during workflow ingestion, projecting them as `IO_SCHEMA` file types automatically.

* **Sidecar Files:** For WDL workflows or legacy pipelines, authors can manually bundle the `.schema.json` file as an associated file in their TRS submission.

* **Agent-Driven Authoring:** If a schema is missing, human users or AI agents can draft the JSON Schema themselves for a workflow they wish to run. While this represents a one-time upfront effort, the resulting schema provides a permanent, reusable contract for all future runs across all compliant orchestrators.

### 11.2 Applicability Beyond Genomics (MLOps)

The GA4GH IO Profile is uniquely positioned to bridge the gap between bioinformatics and MLOps. Machine learning workloads heavily rely on strict hyperparameter definitions (learning rates, batch sizes, categorical enums) and dataset shapes—structures perfectly suited for JSON Schema Draft 2020-12. By adopting this profile, a federated registry could seamlessly catalog PyTorch training pipelines alongside genomic aligners, fully describing both their hyperparameter spaces and expected output model artifacts using the exact same standard.

Given this immense cross-domain potential, further usage details, vocabulary extensions, and integration strategies for data science workloads should be actively explored in collaboration with the new **GA4GH AI Work Stream** and the **Federated ML Working Group**.

### 11.3 Security vs. Client-Side UX

It is important to explicitly distinguish between UX optimization and true system security. Complex client-side validation (enabled by this schema) is a "shift-left" operational strategy. It prevents users from submitting malformed data that will ultimately crash hours into a cloud run, saving significant time and compute costs.

However, client-side validation is *not* a security boundary. A malicious actor may still be able to bypass a UI and `POST` malformed data directly to a public API endpoint. True security (such as preventing shell injection in the execution layer or enforcing strict hardware memory limits) remains the sole responsibility of the API gateway and the underlying execution engine.

### 11.4 Synergies with RO-Crate Profiles

RO-Crate has emerged as a premier standard for packaging research data and computational metadata, making them highly FAIR. However, core RO-Crate does not natively provide execution specifications or results packaging; instead, it relies on specific **RO-Crate Profiles** to provide these features.

The proposed IO Profile complements these RO-Crate profiles perfectly:

* **Workflow RO-Crate:** A `.schema.json` file can be neatly packaged alongside the execution logic. In this model, the RO-Crate manifest (`ro-crate-metadata.json`) handles the rich semantic metadata (author, license, historical provenance), while our GA4GH JSON Schema acts as the strict, machine-readable validation contract dictating exactly *how* a client or agent must format the parameters to execute it via an API.

* **Workflow Run RO-Crate Profiles:** Profiles designed to capture execution history (e.g., *Process Run Crate*, *Workflow Run Crate*, and *Provenance Run Crate*) record the *actual* inputs and outputs of a specific run instance. The GA4GH IO Schema serves as the definitive structural template for these runs. Auditing tools can mathematically validate that a Provenance Run Crate matches the expected semantic shape and parameter bounds declared by the original author.

* **Five Safes RO-Crate:** This profile extends run crates for use in Trusted Research Environments (TREs). The strict parameter validation and shift-left error catching enabled by the IO Schema perfectly align with the rigorous security and auditing postures required by TRE boundaries.

## 12. Next Steps

To drive adoption and prove out the utility of the IO Schema Profile, we propose the following immediate next steps:

1. **Schema Translation Tooling:** Develop lightweight, open-source translation scripts to convert existing `nextflow_schema.json` and CWL `CommandLineTool` inputs into compliant GA4GH IO Profile schemas.

2. **AI Agent Reference Implementations:** Publish a reference implementation of an LLM agent instructed to "auto-draft" compliant IO Schemas.

3. **End-to-End Proof of Concept (PoC):** Construct a sandbox environment featuring a mock TRS registry hosting `.schema.json` files, a generic frontend (e.g., via `react-jsonschema-form`) rendering input forms and compiling WES requests, and a proxy WES gateway enforcing server-side validation against the schema prior to execution.

4. **Formal Specification Submission:** Following the PoC, submit the IDL schema structure, the `x-ga4gh-*` vocabulary, and the proposed API modifications to the GA4GH Federated Analysis Work Stream for formal standardization review.
