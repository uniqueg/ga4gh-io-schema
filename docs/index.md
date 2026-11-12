# GA4GH IO Schema Profile

--8<-- "README.md:synopsis"

## Executive summary

This document proposes the creation of a **JSON Schema Profile**—an Interface Definition Language (IDL) acting as the "OpenAPI specification" for computational workflows and modular analytical components.

Currently, computational tasks are tightly coupled to their underlying execution engines (e.g., Nextflow, CWL, WDL). This profile establishes a strict, machine-readable contract for inputs and outputs that sits *above* these execution languages. By defining the public presentation of a workload rather than its execution mechanics, this standard enables any generic web portal to automatically generate UI forms, allows metadata catalogs to seamlessly understand outputs, and provides AI agents with the deterministic schemas required for workflow composition.

While this standard seamlessly integrates with the GA4GH Federated Analysis ecosystem (TRS, WES, DRS) as a primary benefactor, it is fundamentally **domain-agnostic** and engine-independent, capable of describing generic ETL jobs or machine learning pipelines just as effectively as genomic aligners.

## Contents

- [Motivation](motivation.md): the usability gap, goals, non-goals and the
  concept of a universal compute IDL.
- [Specification](specification/index.md): the keywords, the output contract,
  the meta-schema, conformance and examples.
- [Rationale and related work](rationale.md): the ecosystem survey, why no
  existing solution is adopted, applicability beyond genomics and RO-Crate
  profiles.
- [Security considerations](security.md): what validation with the profile
  does and doesn't protect against.
- [Tools](tools/index.md): the validator (CLI and Python API) and converters.
- [Adoption](adoption/index.md): the adoption path and guides for TRS, WES,
  and portals and clients.
- [Roadmap](roadmap.md): next steps and the history of this proposal.
- [Development](development.md): tests and checks for contributors.

## License

The documentation is licensed under
[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/), the code and
schemas under [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0) (see
`REUSE.toml` in the
[repository](https://github.com/uniqueg/ga4gh-io-schema)).
