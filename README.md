<!--
SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>

SPDX-License-Identifier: Apache-2.0
-->

# GA4GH IO Schema Profile (Incubator)

<!-- --8<-- [start:synopsis] -->
> Incubating a proposed GA4GH JSON Schema Profile to standardize workflow and modular component I/O across WES and Registries, featuring a Python validation package.

Currently, the GA4GH Federated Analysis API ecosystem (TRS, WES, DRS) provides a robust infrastructure for executing workloads, but lacks a standardized, machine-readable contract for describing workflow and modular component parameters.

This repository incubates a proposed **GA4GH JSON Schema Profile** (and accompanying meta-schema). By establishing a strict I/O contract that sits above underlying workflow languages (e.g., CWL, WDL, Nextflow), this profile enables generic WES clients to automatically generate UI forms, validate complex inputs (like sample tables) client-side, and allows AI agents to deterministically construct valid execution payloads.
<!-- --8<-- [end:synopsis] -->

## Documentation

The documentation is on [Read the Docs](https://ga4gh-io-schema.readthedocs.io/):

- [Motivation](https://ga4gh-io-schema.readthedocs.io/en/latest/motivation/): the usability gap, goals and non-goals
- [Specification](https://ga4gh-io-schema.readthedocs.io/en/latest/specification/): keywords, output contract, meta-schema, conformance and examples
- [Rationale and related work](https://ga4gh-io-schema.readthedocs.io/en/latest/rationale/): ecosystem survey and design decisions
- [Security considerations](https://ga4gh-io-schema.readthedocs.io/en/latest/security/)
- [Tools](https://ga4gh-io-schema.readthedocs.io/en/latest/tools/): the validator (CLI and Python API) and converters
- [Adoption](https://ga4gh-io-schema.readthedocs.io/en/latest/adoption/): TRS, WES, portals and clients
- [Roadmap](https://ga4gh-io-schema.readthedocs.io/en/latest/roadmap/)
- [Development](https://ga4gh-io-schema.readthedocs.io/en/latest/development/): tests and checks

The sources of the documentation are in [`docs/`](docs/).

---

## Contribute

Contributions, issues, and feature requests are welcome! If you have suggestions for new UI widgets, ontology mappings, or tabular data validation strategies, please open an issue or submit a pull request. See [Development](https://ga4gh-io-schema.readthedocs.io/en/latest/development/) for the checks that changes must pass.

---

## License

This repository is multi-licensed in compliance with the [REUSE specification](https://reuse.software/):

- **Code, schemas, tests and this README (`/src`, `/schemas`, `/tests`, `README.md`):** Licensed under **Apache-2.0**.
- **Documentation (`/docs`):** Licensed under **CC-BY-4.0**.

Each file's SPDX header, or its entry in `REUSE.toml`, is authoritative; `reuse lint` checks them in CI. Please see the [`LICENSE`](LICENSE) file and `REUSE.toml` for complete details and mapping. Full license texts are located in the `/LICENSES` directory.

---

## Contacts

- **Maintainer:** ELIXIR On-Cloud / GA4GH Contributors
- **Repository:** [https://github.com/uniqueg/ga4gh-io-schema](https://github.com/uniqueg/ga4gh-io-schema)
