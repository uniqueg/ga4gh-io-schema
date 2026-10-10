<!--
SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>

SPDX-License-Identifier: CC-BY-4.0
-->

# GA4GH Schema Profile Proposal for Workflow and Tool Inputs/Outputs

## 1. Versioning Matrix

| Version | Date | Author | Notes |
| ----- | ----- | ----- | ----- |
| **v0.1** | 2026-10-10 | Alexander Kanitz | Initial Draft: Ecosystem survey, evaluation, and GA4GH JSON Schema Profile proposal. |

## 2. Executive Summary

This document proposes the creation of a **GA4GH JSON Schema Profile** specifically designed to describe the inputs and outputs of computational workflows and individual tool executables. We propose that this schema be formally supported as a new, distinct file type within the Tool Registry Service (TRS). By establishing a strict, machine-readable contract for I/O that sits above the underlying workflow language (e.g., WDL, Nextflow) or containerized tool, clients can effectively and deterministically operationalize both Workflow Execution Service (WES) and Task Execution Service (TES) APIs. This profile bridges the gap between static registries and dynamic, interactive execution environments for both human users and AI agents.

## 3. Motivation

Currently, the GA4GH Cloud API ecosystem (TRS, WES, TES, DRS) provides a robust infrastructure for finding and executing workloads. However, it suffers from a critical "usability gap" regarding I/O definitions for both full workflows and standalone tool executables:

* **Opaque Payloads:** WES and TES APIs often receive and return opaque JSON payloads or unstructured directories of files. Tool executables are generally poorly described in terms of their APIs, making it hard to know exactly what parameters a TES task requires.

* **Lack of UI Generation:** Without a universally standardized schema format, WES/TES clients cannot automatically generate dynamic, type-safe HTML forms for users to configure and launch runs.

* **AI Agent Friction:** Smart AI agents rely on well-defined, machine-readable function schemas to confidently prepare valid run calls. Ambiguous, DSL-specific parameter definitions (e.g., WDL `parameter_meta`) or undocumented tool entrypoints lead to hallucinations and failed API calls.

* **The "Black Box" Output Problem:** Outputs are currently treated as nondescript files by execution engines. There is no standard mechanism to tell a client that a specific output file from a WES/TES run is a VCF meant to be rendered in an interactive genome browser, hindering seamless downstream analysis.

This lack of standardization prevents the hassle-free, off-the-shelf deployment of workflows and tools deposited in registries like WorkflowHub and Dockstore. Closing this gap will drastically lower the barrier to entry for platform developers, human end-users, and machine agents, accelerating GA4GH ecosystem adoption.

## 4. Goals

1. **Automated UI Generation:** Enable any generic WES or TES client to automatically render intuitive, strictly validated input forms for any registered tool or workflow.

2. **AI & Machine Interoperability:** Provide a deterministic, universally understood schema format that AI agents can natively use to construct valid WES/TES run requests and accurately parse outputs.

3. **Complex Data Validation:** Standardize the validation of complex objects, specifically multi-column sample tables (manifests), before a compute job is even triggered.

4. **Interactive Output Ecosystems:** Semantically annotate outputs with visualization hints to enable IDEs, dashboards, and downstream pipelines to natively understand and render interactive components (e.g., charts, genome browsers).

## 5. Scope

**In Scope:**

* Definition of a standardized, technology-agnostic schema framework and profile for describing tool and workflow I/O.

* Standardized semantic annotations (e.g., DRS URI mappings, ontology links).

* Standardized UI and visualization rendering hints for outputs.

* Integration recommendations for TRS (as a new `ToolFile` type) to serve these schemas to WES/TES clients.

**Out of Scope:**

* Modifications to existing workflow language specifications (CWL, WDL, Nextflow, etc.).

* Modifications to the core HTTP WES or TES API specifications.

* The internal execution, parsing, or scheduling logic of workflow engines or task executors.

* Schema definitions for highly interactive MLOps telemetry.

## 6. Ecosystem Survey

To identify an optimal standard for the GA4GH ecosystem, we surveyed existing input and output descriptor solutions across prominent bioinformatics workflow languages and data packaging standards.

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
| **CWL** | High (Strict typing) | High (EDAM native) | None | Manual |
| **Nextflow** | Low (Directory structures) | None Natively | External (MultiQC) | Manual |
| **WDL** | Medium (Typed primitives) | Custom (`parameter_meta`) | Platform Dependent | Manual |
| **Galaxy** | Very High (Tool XML) | High (Internal Datatypes) | High (Display Apps) | Medium |
| **RO-Crate** | Medium (JSON-LD) | High (Bioschemas `FormalParameter`) | Low | High (Frictionless) |
| **Data Packages** | High (for tabular data) | Medium | Low | High (Frictionless) |

### 6.3 Evaluation of Existing Standards

An analysis of the survey matrices reveals a fragmented landscape. While brilliant solutions exist within individual silos, **no single existing standard meets all the cross-platform requirements of a generic GA4GH API ecosystem.**

* **Tight Ecosystem Coupling (CWL & Galaxy):** Both CWL (via Schema Salad) and Galaxy (via Tool XML) offer incredibly robust, strictly typed I/O definitions with native ontology support. However, they are deeply coupled to their respective execution engines. Using CWL's Schema Salad as a generic payload validator for a WDL-backed WES would require clients to implement complex Avro/JSON-LD parsers, creating an unreasonable adoption barrier.

* **Lack of Standardization (WDL):** WDL relies on the completely unstandardized `parameter_meta` block. Because authors can place arbitrary key-value pairs here, UI generators and AI agents cannot deterministically parse it across different repositories.

* **Neglected Output Definitions (Nextflow & Snakemake):** Nextflow's recent adoption of JSON Schema via the `nf-schema` plugin, and Snakemake's integration with PEP (Portable Encapsulated Projects), represent massive leaps forward for *input* validation. However, both platforms largely ignore structured *output* schemas. Execution clients are left blindly receiving directories of files without the semantic context needed to trigger downstream visualizations or subsequent workflow steps.

**Conclusion:** We cannot adopt an existing ecosystem's standard as-is. We need a solution that takes the decoupling and ubiquity of Nextflow's JSON Schema approach, marries it with the semantic ontology strength of CWL, and explicitly mandates bi-directional (Input and Output) definitions.

## 7. Proposed Solution: Architecture & Rationale

Based on the evaluation above, the proposed solution is to utilize **JSON Schema (Draft 2020-12)**, heavily augmented by a custom **GA4GH Meta-Schema Profile** that introduces specific `x-ga4gh-*` extension vocabularies.

**The authoritative meta-schema defining this profile is the core deliverable of this proposal and can be reviewed here: [`../schemas/ga4gh-io-profile.schema.json`](https://raw.githubusercontent.com/uniqueg/ga4gh-io-schema/main/schemas/ga4gh-io-profile.schema.json).**

Below is a detailed breakdown of the rationale behind this architecture, leading up to concrete examples of the schema in action.

### 7.1 Why JSON Schema?

* **Universally Understood:** JSON Schema is the backbone of the modern RESTful web. Validation libraries and UI generators (e.g., React JSON Schema Form) exist in every major programming language natively.

* **AI-Native Interoperability:** Modern LLMs natively use JSON Schema for "Structured Outputs" and "Tool Calling". Adopting it immediately makes the entire catalog of tools and workflows in GA4GH registries AI-ready.

* **Language Agnostic:** It sits cleanly above CWL, WDL, Nextflow, and bare-metal container tools without requiring modifications to those underlying languages.

### 7.2 The Bi-Directional Mandate: Inputs and Outputs

To solve the "Black Box Output" problem, the GA4GH meta-schema strictly requires the root of the JSON document to define both `inputs` and `outputs` properties.

* The `inputs` block provides the contract for WES/TES payload submission and UI form generation.

* The `outputs` block provides the contract for parsing workflow/tool outputs post-execution, allowing clients to map resulting files to UI visualization widgets (e.g., Genome Browsers) or downstream analysis pipelines.

### 7.3 Borrowing, Adapting, and Improving: The `x-ga4gh-*` Vocabulary

While JSON Schema provides the structural validation (types, minimums, required fields), it lacks the bioinformatics-specific context required by GA4GH clients. To solve this, we systematically reviewed how existing communities extend JSON Schema and formulated a standardized `x-ga4gh-*` extension vocabulary.

**1. Tabular Validation (Adapted from `nf-schema` vs PEP)**
Bioinformatics heavily relies on CSV/TSV sample sheets. Standards like PEP (Portable Encapsulated Projects) used by Snakemake provide excellent sample metadata validation, but they require ecosystem-specific client parsers (like Python's `peppy`) to resolve the rules, which is too heavy a lift for a generic web client or WES engine written in Go or Java. `nf-schema` solved this in a self-contained way by allowing authors to define a schema for the *contents* of a file directly within the JSON.

We adapt this as `x-ga4gh-tabular-schema`. By attaching this to a string input, any standard JSON client knows it must pre-parse the CSV and validate its internal columns against this nested schema *before* submitting a workflow or task run.

**2. UI Rendering Hints (Inspired by `nf-core`)**
Community projects often inject custom hints to control how web interfaces render forms. We formalize these:

* `x-ga4gh-hidden`: A boolean flag to hide advanced parameters from default user views.

* `x-ga4gh-fa-icon`: Support for FontAwesome classes to add visual flair to UI forms.

* `x-ga4gh-ui-widget`: A standardized vocabulary (e.g., `genome-browser`, `plotly`, `file-upload`) that explicitly tells the client *how* to render an input control or an output file.

**3. Resolving Redundancy: Titles and Descriptions**
Many custom schemas feature redundant properties like `short_label` and `description`, or `description` (for short text) and `help_text` (for long-form markdown). This clutters the schema and causes inconsistent rendering. Instead, we propose relying strictly on the native JSON Schema `title` field for concise, human-readable labels (e.g., "Reference FASTA"), and the native `description` field for detailed help text. To empower the `description` field, we introduce `x-ga4gh-description-format` (enum: `plain_text`, `markdown`, `rst`). This elegantly instructs the UI on how to parse and render the single description field without inventing new text properties.

**4. Semantic Typing and Data Locality**
To bridge the gap left by JSON Schema's lack of scientific context, we introduce:

* `x-ga4gh-ontology`: Allows mapping a standard string or file to an EDAM format URI (borrowing the best feature of CWL).

* `x-ga4gh-drs-uri`: A boolean flag explicitly marking a string as a Data Repository Service endpoint, allowing clients to proactively initiate DRS-to-local path resolution.

## 8. Proposed Schema Examples

Below are two illustrative examples of the GA4GH JSON Schema Profile. Note that both explicitly reference the proposed GA4GH Meta-Schema (`https://raw.githubusercontent.com/uniqueg/ga4gh-io-schema/main/schemas/ga4gh-io-profile.schema.json`) via the `$schema` keyword to enforce the presence of the structural and custom annotations discussed in Section 7.

### 8.1 Example 1: Full Workflow (WES) with Tabular Validation

This example demonstrates how to validate a workflow that takes a CSV sample sheet as input.

```json
{
  "$schema": "https://raw.githubusercontent.com/uniqueg/ga4gh-io-schema/main/schemas/ga4gh-io-profile.schema.json",
  "$id": "https://ga4gh.org/schemas/workflow-io-profile/v1",
  "title": "RNA-Seq Pipeline",
  "description": "Bulk RNA-Seq alignment and QC workflow.",
  "type": "object",
  "properties": {
    "inputs": {
      "type": "object",
      "properties": {
        "sample_manifest": {
          "type": "string",
          "format": "uri",
          "title": "Sample Manifest",
          "description": "Path to a CSV sample sheet containing biological replicate information.",
          "x-ga4gh-drs-uri": true,
          "x-ga4gh-tabular-schema": {
            "type": "array",
            "description": "Validates the internal columns of the provided CSV file.",
            "items": {
              "type": "object",
              "properties": {
                "sample_id": { "type": "string", "title": "Sample ID", "pattern": "^[a-zA-Z0-9_]+$" },
                "fastq_1": { "type": "string", "title": "Read 1 FASTQ", "format": "uri" },
                "condition": { "type": "string", "title": "Condition", "enum": ["control", "treatment"] }
              },
              "required": ["sample_id", "fastq_1", "condition"]
            }
          }
        }
      },
      "required": ["sample_manifest"]
    },
    "outputs": {
      "type": "object",
      "properties": {
        "qc_report": {
          "type": "string",
          "format": "uri",
          "title": "QC HTML Report",
          "x-ga4gh-ui-widget": "html-iframe"
        }
      }
    }
  }
}
```

### 8.2 Example 2: Standalone Tool (TES)

This standard works equally well for defining standalone tool executables shipped to a Task Execution Service (TES).

```json
{
  "$schema": "https://raw.githubusercontent.com/uniqueg/ga4gh-io-schema/main/schemas/ga4gh-io-profile.schema.json",
  "$id": "https://ga4gh.org/schemas/tool-io-profile/v1",
  "title": "BWA MEM Aligner",
  "description": "Burrows-Wheeler Aligner for short read mapping.",
  "type": "object",
  "properties": {
    "inputs": {
      "type": "object",
      "properties": {
        "reference_fasta": {
          "type": "string",
          "format": "uri",
          "title": "Reference FASTA",
          "x-ga4gh-ontology": "http://edamontology.org/format_1929"
        },
        "read_1": {
          "type": "string",
          "format": "uri",
          "title": "Read 1 FASTQ"
        },
        "threads": {
          "type": "integer",
          "minimum": 1,
          "default": 4,
          "title": "CPU Threads"
        }
      },
      "required": ["reference_fasta", "read_1"]
    },
    "outputs": {
      "type": "object",
      "properties": {
        "alignment_bam": {
          "type": "string",
          "format": "uri",
          "title": "Aligned BAM",
          "x-ga4gh-ontology": "http://edamontology.org/format_2572",
          "x-ga4gh-ui-widget": "genome-browser"
        }
      }
    }
  }
}
```

## 9. Discussion

### 9.1 Adoption Plan (Ecosystem Independence)

The success of this profile does not require the "approval" or modification of CWL, WDL, or Nextflow specifications. Adoption can be driven organically through multiple avenues across the ecosystem:

* **Registry Ingestion:** Platforms like Dockstore and WorkflowHub can implement server-side parsers that automatically extract and generate this JSON Schema from existing `Schema Salad` (CWL) or `nextflow_schema.json` files during workflow ingestion.

* **Sidecar Files:** For WDL workflows or arbitrary TES tool containers, authors can simply upload the `.ga4gh.schema.json` file as an associated file in their TRS submission.

* **Platform Auto-Generation:** Analysis platforms (WES/TES clients) can dynamically auto-generate these schemas by parsing raw workflow definitions upon import, bypassing the need for a TRS-based registry entirely.

* **Community Sourcing:** For popular or legacy workflows and tools, the community can centrally crowd-source and maintain schema profiles in open repositories, acting as a shared public good.

* **User and Agent-Driven Authoring:** If a schema is entirely missing, human users or AI agents can write the schema themselves for a workflow they wish to run. While this represents a one-time effort upfront, the resulting schema provides a permanent, reusable contract for all future runs.

### 9.2 Suitability for Data Science / MLOps

While the GA4GH execution APIs (like WES) have limitations regarding the highly interactive telemetry required by MLOps orchestrators, the **GA4GH JSON Schema Profile itself is a perfect fit for describing Data Science workloads**.

* Machine learning workloads heavily rely on strict hyperparameter definitions (learning rates, batch sizes, categorical enums) and dataset shapes.

* JSON Schema is the native language of these configurations. By adopting this profile, a TRS instance could seamlessly catalog ML training pipelines or inference microservices, fully describing their hyperparameter spaces and expected output model artifacts using the exact same standard used for genomics.

### 9.3 Security and Client-Side Validation

An additional benefit of this schema profile is operational security and cost-reduction. By offloading complex validation (e.g., regex checking for valid sample IDs, ensuring numerical inputs fall within safe hardware limits) to the client *before* a WES or TES submission, we prevent malformed data from triggering expensive, doomed-to-fail cloud compute jobs, while also neutralizing simple injection attacks common in poorly sanitized bash scripts or workflows executed via TES or WES, respectively.

### 9.4 Interplay with RO-Crate

RO-Crate has become a premier standard for packaging computational workflows, making them highly FAIR (Findable, Accessible, Interoperable, Reusable). While RO-Crate utilizes semantic web principles (JSON-LD and Bioschemas) to describe *what* a workflow is and *who* authored it, it is not optimized as a strict, functional validation engine for APIs.

The proposed GA4GH JSON Schema Profile is designed to complement, not compete with, RO-Crate. A `.ga4gh.schema.json` file can be neatly packaged within a Workflow RO-Crate. In this synergistic model, the RO-Crate manifest (`ro-crate-metadata.json`) handles the rich semantic provenance and metadata, while the GA4GH JSON Schema acts as the strict, machine-readable validation contract dictating exactly *how* a client or agent must format the parameters to actually execute it.

### 9.5 Minimal Recommendations for GA4GH APIs

To improve integration of this profile with the existing GA4GH API product ecosystem, the following minimal conventions are recommended:

* **TRS (Tool Registry Service):** TRS implementations should formally recognize schema files. We recommend TRS introduce a new enum value for the `ToolFile` `file_type`, such as `IO_SCHEMA`. The exact nature of the schema (e.g., GA4GH JSON Schema Profile) can be defined via content-type or other metadata. This allows clients to instantly discover and fetch the I/O contract independently from the executable workflow.

* **WES (Workflow Execution Service) & TES (Task Execution Service):** Client-side validation is the primary goal; however, execution servers should implement "trust but verify." If a WES or TES implementation has access to the schema (either fetched from TRS prior to execution, or provided directly by the client), the server *should* attempt to validate the incoming JSON payload against it.

* **Deterministic Error Handling:** If server-side validation fails, WES and TES APIs should return an `HTTP 400 Bad Request`. Crucially, the error response body should explicitly emit the specific JSON Schema validation error path (e.g., `$.inputs.sample_manifest[2].condition: value not in enum`), providing human users and AI agents with immediate, actionable debugging feedback without having to dig through execution engine logs.

## 10. Next Steps

To transition this profile from a draft concept to an impactful standard within the ecosystem, we propose the following practical roadmap:

* **Community Presentation & Review:** Schedule a formal review session with the GA4GH Federated Analytics Work Stream (formerly the Cloud Work Stream) to present the v0.1 draft, meta-schema, and the Python reference validator for initial feedback.
* **Schema Translation Tooling:** Develop reference parsers to automatically translate existing definitions into the GA4GH IO Profile. This will target three distinct paradigms to prove broad applicability:
  * Languages with baked-in descriptors (e.g., CWL or Galaxy XML).
  * Languages relying on bespoke JSON Schema extensions (e.g., Nextflow `nf-schema` or Snakemake).
  * Native tool-level CLI argument parsers (e.g., Python's `argparse`).
* **AI-Assisted Generation:** Prototype an AI agent capable of statically analyzing raw workflow definitions or tool source code to dynamically draft baseline IO schemas, lowering the adoption barrier for legacy pipelines.
* **End-to-End Proof of Concept (WES/TES):** Build a lightweight frontend client that consumes these generated schemas to dynamically render input forms, execute client-side validation, and successfully dispatch real-world workloads to a WES or TES endpoint.
* **Registry Engagement (Dockstore / WorkflowHub):** Leverage the success of the end-to-end PoC to demonstrate concrete value to primary registries, providing the necessary evidence to advocate for the official addition of an `IO_SCHEMA` file type in the TRS specification.
* **Formal Specification Draft:** Pending successful PoCs, translate this incubation proposal into a formal specification document for adoption as a standard under the Federated Analytics Work Stream.
