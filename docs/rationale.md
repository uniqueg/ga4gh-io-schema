# Rationale and related work

## Ecosystem survey and the "15th standard" dilemma

We surveyed existing input and output descriptor solutions across prominent computational workflow languages and data packaging standards to determine if an existing format could serve as a universal IDL.

### Input schema landscape

| Ecosystem / Standard | Primary Schema Standard | Ecosystem Coupling | UI Generation Capable | Complex Data (Sample Tables) |
| ----- | ----- | ----- | ----- | ----- |
| **Nextflow** | JSON Schema (`nf-schema`) | Low | High | High (via CSV validation rules) |
| **CWL** | Schema Salad (Avro/JSON-LD) | High | Medium | Typed Nested Records |
| **WDL** | `parameter_meta` (Custom) | Medium | Platform-specific | Opaque Files |
| **Snakemake** | JSON Schema & PEP | Low | Medium | High (Native PEP Support) |
| **Galaxy** | Tool XML | Very High | Very High | Collections (Paired/List) |

### Output schema landscape

| Ecosystem / Standard | Output Definition Strength | Semantic Ontology Support | UI Visualization Hints | Tabular Schema Integration |
| ----- | ----- | ----- | ----- | ----- |
| **Nextflow** | Low (Directory structures)\* | None Natively | External (MultiQC) | Manual |
| **CWL** | High (Strict typing) | High (EDAM native) | None | Manual |
| **WDL** | Medium (Typed primitives) | Custom (`parameter_meta`) | Platform Dependent | Manual |
| **Snakemake** | Low (File patterns) | None Natively | External | Manual |
| **Galaxy** | Very High (Tool XML) | High (Internal Datatypes) | High (Display Apps) | Medium |

*(Note: The Nextflow community recognizes this gap and is actively working to standardize output schemas via initiatives like PR #6900 `nextflow_spec.json`).*

### Why not adopt an existing solution?

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

See [Keywords](specification/keywords.md) for the resulting profile.

## Applicability beyond genomics (MLOps)

The GA4GH IO Profile is uniquely positioned to bridge the gap between bioinformatics and MLOps. Machine learning workloads heavily rely on strict hyperparameter definitions (learning rates, batch sizes, categorical enums) and dataset shapes—structures perfectly suited for JSON Schema Draft 2020-12. By adopting this profile, a federated registry could seamlessly catalog PyTorch training pipelines alongside genomic aligners, fully describing both their hyperparameter spaces and expected output model artifacts using the exact same standard.

Given this immense cross-domain potential, further usage details, vocabulary extensions, and integration strategies for data science workloads should be actively explored in collaboration with the new **GA4GH AI Work Stream** and the **Federated ML Working Group**.

## Synergies with RO-Crate profiles

RO-Crate has emerged as a premier standard for packaging research data and computational metadata, making them highly FAIR. However, core RO-Crate does not natively provide execution specifications or results packaging; instead, it relies on specific **RO-Crate Profiles** to provide these features.

The proposed IO Profile complements these RO-Crate profiles perfectly:

* **Workflow RO-Crate:** A `.schema.json` file can be neatly packaged alongside the execution logic. In this model, the RO-Crate manifest (`ro-crate-metadata.json`) handles the rich semantic metadata (author, license, historical provenance), while our GA4GH JSON Schema acts as the strict, machine-readable validation contract dictating exactly *how* a client or agent must format the parameters to execute it via an API.

* **Workflow Run RO-Crate Profiles:** Profiles designed to capture execution history (e.g., *Process Run Crate*, *Workflow Run Crate*, and *Provenance Run Crate*) record the *actual* inputs and outputs of a specific run instance. The GA4GH IO Schema serves as the definitive structural template for these runs. Auditing tools can mathematically validate that a Provenance Run Crate matches the expected semantic shape and parameter bounds declared by the original author.

* **Five Safes RO-Crate:** This profile extends run crates for use in Trusted Research Environments (TREs). The strict parameter validation and shift-left error catching enabled by the IO Schema perfectly align with the rigorous security and auditing postures required by TRE boundaries.
