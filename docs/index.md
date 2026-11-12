# GA4GH IO Schema Profile

--8<-- "README.md:synopsis"

## Executive summary

This document proposes a **JSON Schema profile** that describes the inputs and outputs of computational workflows and workflow components, in the role that an OpenAPI description plays for a web API.

Today, the inputs and outputs of a workflow are described in the language of its engine (e.g., Nextflow, CWL, WDL), and each engine does it differently. The profile adds an engine-neutral contract for inputs and outputs that sits *above* these languages: it describes the public interface of a workflow, not how the workflow runs. With it, portals can render input forms (through an adapter that reads the `x-ga4gh-*` keywords, see [Portals and clients](adoption/portals.md)), catalogues and clients can interpret outputs, and AI agents can derive tool definitions for building run requests.

The profile is designed for the GA4GH APIs for federated analysis (TRS, WES, DRS) and for workflows in the life sciences. Whether it also suits other kinds of workloads, such as machine learning pipelines, is an [open question](roadmap.md#open-questions).

## Contents

- [Motivation](motivation.md): the usability gap, goals, non-goals and the
  concept of an interface description above workflow languages.
- [Specification](specification/index.md): the keywords, the output contract,
  the meta-schema, conformance and examples.
- [Rationale](rationale.md): the ecosystem survey and why no existing
  solution is adopted.
- [Related work](related-work.md): how the profile relates to overlapping
  standards and tools (WES, Nextflow, RO-Crate, MCP, OGC and others).
- [Security considerations](security.md): what validation with the profile
  does and doesn't protect against.
- [Tools](tools/index.md): the validator (CLI and Python API) and converters.
- [Adoption](adoption/index.md): the adoption path and guides for TRS, WES,
  and portals and clients.
- [Roadmap](roadmap.md): next steps, open questions and the history of this
  proposal.
- [Development](development.md): tests and checks for contributors.

## License

The documentation is licensed under
[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/), the code and
schemas under [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0) (see
`REUSE.toml` in the
[repository](https://github.com/uniqueg/ga4gh-io-schema)).
