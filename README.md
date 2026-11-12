<!--
SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>

SPDX-License-Identifier: Apache-2.0
-->

# GA4GH IO Schema Profile (Incubator)
>
> Incubating a proposed GA4GH JSON Schema Profile to standardize workflow and modular component I/O across WES and Registries, featuring a Python validation package.

---

## Table of Contents

- [Overview](#overview)
- [Getting Started](#getting-started)
- [Usage](#usage)
- [Development & Testing](#development--testing)
- [Deployment](#deployment)
- [Contribute](#contribute)
- [License](#license)
- [Contacts](#contacts)

---

## Overview

Currently, the GA4GH Federated Analysis API ecosystem (TRS, WES, DRS) provides a robust infrastructure for executing workloads, but lacks a standardized, machine-readable contract for describing workflow and modular component parameters.

This repository incubates a proposed **GA4GH JSON Schema Profile** (and accompanying meta-schema). By establishing a strict I/O contract that sits above underlying workflow languages (e.g., CWL, WDL, Nextflow), this profile enables generic WES clients to automatically generate UI forms, validate complex inputs (like sample tables) client-side, and allows AI agents to deterministically construct valid execution payloads.

Please see the [Formal Proposal Document](docs/proposal_ga4gh_io_schema.md) for full context, ecosystem survey, and design decisions.

---

## Getting Started

### Installation

To install the validator tool and all development dependencies for local testing, clone the repository and install it in editable mode:

```bash
git clone https://github.com/uniqueg/ga4gh-io-schema.git
cd ga4gh-io-schema
pip install -e ".[dev]"
```

To install only the validator, run `pip install .` in the cloned repository instead. The package supports Python 3.11 and later, and it ships the meta-schema and its vocabularies, so the validator works offline and outside the repository.

---

## Usage

Once installed, the package exposes a command-line interface to validate your drafted tool or workflow IO schemas against the GA4GH meta-schema.

```bash
ga4gh-io-schema-validator path/to/your-schema.json
```

By default, the validator uses the meta-schema that the schema names in its `$schema` property and resolves the GA4GH meta-schema and vocabularies from the installed package. Use `--meta-schema` (`-m`) to validate against another meta-schema file:

```bash
ga4gh-io-schema-validator path/to/your-schema.json --meta-schema path/to/meta-schema.json
```

Inside your own drafted schemas, you can reference the meta-schema directly to enable IDE autocompletion and validation. The identifier is versioned: it names the release of the profile, not a moving branch.

```json
{
  "$schema": "https://raw.githubusercontent.com/uniqueg/ga4gh-io-schema/v0.3.0/schemas/ga4gh-io-profile.schema.json",
  "$id": "https://example.org/schemas/my-tool/v1"
}
```

The validator checks the `format` keywords of the meta-schema, for example that `$id` is a URI reference and that `x-ga4gh-ontology` is a URI (format checks use the `format-nongpl` extra of `jsonschema`). It checks the schema itself, not the input values that a WES request would send later. If a client also checks those values with `"format": "uri"`, note that DRS URIs with a host name (`drs://drs.example.org/314159`) are valid URIs, but DRS URIs with a compact identifier (`drs://drs.example.org:314159` or `drs://prefix:accession`) are not, because the part after the colon isn't a port number.

---

## Development & Testing

This project enforces a strict "full defense" CI/CD pipeline. All code must pass comprehensive unit tests, static analysis, and licensing checks before being merged.

### 1. Unit Tests (pytest)

Validate the core logic of the Python executable using `pytest`. The test suite uses mock schemas located in `tests/data/`.

```bash
pytest
```

### 2. Code Quality (Ruff)

The codebase uses `Ruff` to enforce strict formatting, linting, and Google-style docstrings.

```bash
ruff format .
ruff check .
```

### 3. Meta-Schema Validation

The GA4GH meta-schemas themselves must strictly conform to the JSON Schema Draft 2020-12 specification. We validate this using `check-jsonschema`.

```bash
check-jsonschema --check-metaschema schemas/ga4gh-io-profile.schema.json
check-jsonschema --check-metaschema schemas/vocabularies/ui-widgets.schema.json
```

### 4. License Compliance (REUSE)

All files must have clear copyright and licensing information compliant with the [REUSE specification](https://reuse.software/). The primary codebase is Apache-2.0, while documentation is CC-BY-4.0.

```bash
reuse lint
```

### 5. Documentation Linting

Markdown files are linted to ensure consistent structure and catch broken links.

```bash
npx markdownlint-cli "**/*.md" --ignore "node_modules"
```

---

## Deployment

As a schema standard, there is no active deployment of a service. The schemas and vocabularies are served statically via raw GitHub URLs. In the future, the goal is to integrate this schema format natively into **TRS (Tool Registry Service)** implementations as a new `IO_SCHEMA` file type.

---

## Contribute

Contributions, issues, and feature requests are welcome! If you have suggestions for new UI widgets, ontology mappings, or tabular data validation strategies, please open an issue or submit a pull request.

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
