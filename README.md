<!--
SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>

SPDX-License-Identifier: Apache-2.0
-->

# GA4GH IO Schema Profile (Incubator)

<!-- --8<-- [start:synopsis] -->
> Incubating a proposed GA4GH JSON Schema Profile to standardize workflow and modular component I/O across WES and Registries, featuring a Python validation package.

The GA4GH APIs for federated analysis (TRS, WES, DRS) let clients find and run workflows, but they have no engine-neutral, machine-readable contract for the inputs and outputs of workflows and workflow components.

This repository incubates a proposed **GA4GH JSON Schema Profile** (and accompanying meta-schema). By establishing an I/O contract that sits above workflow languages (e.g., CWL, WDL, Nextflow), this profile lets WES clients render input forms (through an adapter for the `x-ga4gh-*` keywords), check input values before they submit a run, and derive tool definitions for AI agents that build run requests.
<!-- --8<-- [end:synopsis] -->

## Documentation

The documentation is on [Read the Docs](https://ga4gh-io-schema.readthedocs.io/):

- [Motivation](https://ga4gh-io-schema.readthedocs.io/en/latest/motivation/): the usability gap, goals and non-goals
- [Specification](https://ga4gh-io-schema.readthedocs.io/en/latest/specification/): keywords, outputs model, meta-schema, conformance and examples
- [Rationale](https://ga4gh-io-schema.readthedocs.io/en/latest/rationale/): ecosystem survey and design decisions
- [Related work](https://ga4gh-io-schema.readthedocs.io/en/latest/related-work/): overlapping standards and tools, and how the profile relates to them
- [Security considerations](https://ga4gh-io-schema.readthedocs.io/en/latest/security/)
- [Tools](https://ga4gh-io-schema.readthedocs.io/en/latest/tools/): the validator (CLI and Python API) and converters
- [Adoption](https://ga4gh-io-schema.readthedocs.io/en/latest/adoption/): TRS, WES, portals and clients
- [Roadmap](https://ga4gh-io-schema.readthedocs.io/en/latest/roadmap/)
- [Development](https://ga4gh-io-schema.readthedocs.io/en/latest/development/): tests and checks

The sources of the documentation are in [`docs/`](docs/).

---

## Usage

Install the package from a clone of the repository (Python 3.11 or later)
and validate an IO schema against the profile:

```bash
pip install .
ga4gh-io-schema validate path/to/your-schema.json
```

To convert CWL documents, install the `cwl` extra (`pip install ".[cwl]"`)
and see the
[CWL converter](https://ga4gh-io-schema.readthedocs.io/en/latest/tools/cwl/).

Turn input values into the `workflow_params` of a WES run request (see
[WES parameters](https://ga4gh-io-schema.readthedocs.io/en/latest/tools/wes-params/)):

```bash
ga4gh-io-schema wes-params --schema path/to/your-schema.json --values values.json
```

`ga4gh-io-schema --help` lists the subcommands; see the
[command-line interface](https://ga4gh-io-schema.readthedocs.io/en/latest/tools/cli/)
for input from standard input, `--output`, `--json` and the exit codes.

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
