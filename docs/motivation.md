# Motivation

## The usability gap

Modern computational science relies on a massive, distributed catalog of analytical tools. However, regardless of the scientific domain, a critical "usability gap" exists between static registries (where tools are published) and dynamic clients (human UIs or AI agents that want to run them) due to a lack of universally understood I/O definitions.

* **Opaque Interfaces:** Registries currently serve engine-specific source code. Generic web portals and AI agents cannot safely or reliably parse Nextflow Groovy configurations, WDL `parameter_meta` blocks, or CWL JavaScript expressions to understand what a workload requires. This forces portals into becoming "walled gardens" that only support single workflow languages.

* **The "Black Box" Outputs:** Workflows generate files, but execution engines typically return unstructured lists of URLs or raw directories in their logs. Clients have no semantic context (e.g., "this URL is a VCF", "this URL is an HTML report") to know how to catalog the outputs or automatically render them in interactive visualization widgets.

* **Agentic Friction:** AI agents rely on well-defined JSON schemas to confidently prepare valid API calls. Ambiguous or undocumented parameters lead to hallucinations, failed compute jobs, and broken workflow chaining.

Solving this gap generically unlocks immediate operational benefits for any compute orchestrator. By defining a universal IDL, we turn static registries into fully executable, UI-ready, and AI-navigable catalogs.

## Goals, non-goals, and out of scope

To ensure this standard remains lightweight, universally adoptable, and strictly focused on interface definition, we establish the following boundaries.

### Goals

* **Automated UI Generation:** Enable any generic client or platform to automatically render intuitive, strictly validated input forms for any registered workload using off-the-shelf industry tooling.

* **AI & Machine Interoperability:** Provide a deterministic format that AI agents can natively ingest to construct valid run requests and intelligently chain outputs to downstream inputs.

* **Semantic Output Typing:** Standardize the annotation of output files with visualization hints (e.g., `genome-browser`) and ontology terms, allowing UIs and data catalogs to automatically contextualize execution results.

### Non-goals and out of scope (the defenses)

* **No CLI Generation:** We do not attempt to map JSON input values to POSIX bash commands (e.g., mapping `threads: 4` to `-t 4`). The underlying workflow engine or container wrapper is solely responsible for execution binding.

* **No Raw Container Staging (e.g., Bare TES Tasks):** Low-level container execution (such as submitting bare containers via the GA4GH Task Execution Service) is explicitly out of scope. Those APIs require physical data staging instructions (container paths, mount points), whereas this schema defines high-level semantic intents. Standalone tools are supported by this standard *only* when wrapped as modular workflow units (e.g., a CWL `CommandLineTool` or an `nf-core` module) that handle their own staging via a workflow orchestrator.

* **No Hardware Policy Enforcement:** The schema validates the *shape* and *type* of requests (e.g., ensuring `memory_mb` is an integer). Hardware limit bounds-checking (e.g., rejecting requests over 256GB RAM) is explicitly a server-side authorization and deployment policy, not a schema validation task.

See also [Security considerations](security.md).

## The concept: a universal compute IDL

The core philosophy of this proposal is the strict separation of **Interface** from **Implementation**.

### Domain agnosticism

Computational orchestration is not unique to genomics. Modern bioinformatics is heavily intertwined with Data Science and Machine Learning. Because this profile relies on native JSON Schema, it is perfectly suited to describe the hyperparameter spaces (learning rates, batch sizes, categorical enums) of PyTorch training pipelines or distributed database ETL jobs. The standard treats all computational units as agnostic mathematical functions: they take typed inputs and produce typed outputs.

See also [Applicability beyond genomics](rationale.md#applicability-beyond-genomics-mlops).

### Decoupling interface from execution

Languages like CWL, Galaxy XML, and Nextflow represent the *implementation*. They handle the messy realities of data staging, CLI flag compilation, and resource allocation.

The IO Profile is the *public presentation*. It provides the semantic contract that a UI or AI agent needs to understand the tool, completely isolating the client from the implementation details.

### The translation model

This proposal does not seek to replace CWL, WDL, or Nextflow. Instead, it acts as the universal **export target**. Platforms like Dockstore or WorkflowHub, or the workflow engine communities themselves, can project their complex, engine-specific definitions into this standardized format upon publication. External clients then only have to learn one parser—JSON Schema—to interact with the entire global catalog of computational tools.

See also [Converters](tools/converters.md) and the [adoption path](adoption/index.md#the-adoption-path-ecosystem-independence).
