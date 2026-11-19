# Rationale

## Ecosystem survey and the "15th standard" dilemma

We surveyed how prominent workflow languages and platforms describe inputs and outputs, to find out whether an existing format could serve as the engine-neutral description that this proposal needs. The survey was last checked against the sources in November 2026.

### Input schema landscape

| Ecosystem / Standard | Primary Schema Standard | Ecosystem Coupling | UI Generation Capable | Complex Data (Sample Tables) |
| ----- | ----- | ----- | ----- | ----- |
| **Nextflow** | JSON Schema (`nextflow_schema.json`, checked by [nf-schema](https://nextflow-io.github.io/nf-schema/latest/nextflow_schema/nextflow_schema_specification/)) | Low | High (e.g., nf-core and Seqera Platform launch forms) | High (schemas for sample sheets) |
| **CWL** | Schema Salad types, declared statically; JSON Schema via cwl-utils [`cwl-inputs-schema-gen`](https://github.com/common-workflow-language/cwl-utils) | Medium | Medium | Typed records and arrays, `File` and `Directory` with secondary files |
| **WDL** | Typed `input` section; `parameter_meta` with structured values but no standard keys ([WDL 1.2](https://github.com/openwdl/wdl/blob/wdl-1.2/SPEC.md#parameter-metadata-section)) | Medium | Platform-specific | Structs and typed `File` inputs; no sample-sheet schema |
| **Snakemake** | JSON Schema ([`snakemake.utils.validate`](https://snakemake.readthedocs.io/en/stable/snakefiles/configuration.html#validation)) and PEP | Low | Medium | High (PEP and validation of tabular configuration) |
| **Galaxy** | Tool XML; JSON Schemas of tool parameters served by the API ([galaxyproject/galaxy#23105](https://github.com/galaxyproject/galaxy/pull/23105), merged July 2026) | High | Very High | Collections (Paired/List) |

### Output schema landscape

| Ecosystem / Standard | Output Definition Strength | Semantic Ontology Support | UI Visualization Hints | Tabular Schema Integration |
| ----- | ----- | ----- | ----- | ----- |
| **Nextflow** | Medium (typed workflow outputs, stable since [25.10](https://docs.seqera.io/nextflow/migrations/25-10))\* | None Natively | External (MultiQC) | Manual |
| **CWL** | High (Strict typing) | High (EDAM terms in `format`) | None | Manual |
| **WDL** | Medium (Typed outputs) | Custom (`parameter_meta`) | Platform Dependent | Manual |
| **Snakemake** | Low (File patterns) | None Natively | External | Manual |
| **Galaxy** | Very High (Tool XML) | High (Internal Datatypes) | High (Display Apps) | Medium |

*(Note: Nextflow's workflow outputs are declared in the pipeline code, not in `nextflow_schema.json`. The draft design record [nextflow-io/nextflow#6900](https://github.com/nextflow-io/nextflow/pull/6900), "ADR: Pipeline spec", proposes a pipeline spec that adopts the nf-core schema for inputs, adds outputs, and can be generated from the pipeline code.)*

### Why not adopt an existing solution?

None of the surveyed formats is engine-neutral:

* **CWL & Galaxy:** Both describe inputs in detail, and their inputs can be read without running the workflow: CWL declares input types statically (expressions are needed only to run a tool, not to read its inputs), and Galaxy serves JSON Schemas of tool parameters. But the types follow each engine's own data model (e.g., CWL `File` objects with secondary files, Galaxy collections), and the exported schemas carry no ontology terms or viewer hints in a common vocabulary. They are good sources for converters into the profile, not a contract that clients of other engines can use.

* **WDL:** `parameter_meta` holds structured values (strings, numbers, arrays and objects), but WDL defines no standard keys for them, so each platform uses its own. We are not aware of a converter from WDL inputs to JSON Schema.

**The "JSON Schema Adapter" Dilemma:**
Nextflow (`nf-schema`) and Snakemake already use JSON Schema for input validation. A valid question is: *Why not just adopt `nf-schema` as the standard?*

While `nf-schema` is a major inspiration for this proposal, it is not engine-neutral, for three reasons:

1. **Engine-local checks:** Some `nf-schema` keywords are checked by the engine on the paths that the pipeline sees. For example, `exists` makes Nextflow check that a file path exists before the run starts; the [nf-schema documentation](https://nextflow-io.github.io/nf-schema/latest/nextflow_schema/nextflow_schema_specification/) says: "If the parameter is an S3, Azure or Google Cloud URI path, this validation is ignored." A schema served next to a workflow is read by portals and WES servers that don't run the workflow and see other paths, or none at all. The profile therefore leaves such checks to the engine, and converters drop them (and say so) rather than translating them.

2. **No outputs:** `nextflow_schema.json` describes parameters only. Nextflow's workflow outputs are typed since version 25.10, but they are declared in the pipeline code; there is no file that a registry can serve to describe them.

3. **Ecosystem-specific vocabulary:** `nf-schema`'s display keywords (`help_text`, `fa_icon`, `hidden`) serve the nf-core tooling, and it has no keywords for ontology terms or for viewers of outputs.

Therefore, we propose adopting **pure JSON Schema (Draft 2020-12)** as our foundation, stripped of any engine-specific execution directives, and extended with a targeted set of custom `x-ga4gh-*` annotations to support domain-specific semantics and UI rendering.

See [Keywords](specification/keywords.md) for the resulting profile.

## Related work

How the profile relates to other standards and tools that overlap with it,
including RO-Crate and Bioschemas `FormalParameter`, is described in
[Related work](related-work.md).
