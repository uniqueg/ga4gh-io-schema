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

---

## Usage

Once installed, the package exposes a command-line interface to validate your drafted tool or workflow IO schemas against the GA4GH meta-schema.

```bash
ga4gh-io-schema-validator --schema path/to/your-schema.json --meta-schema schemas/ga4gh-io-profile.schema.json
```

Inside your own drafted schemas, you can reference the meta-schema directly to enable IDE autocompletion and validation:

```json
{
  "$schema": "https://raw.githubusercontent.com/uniqueg/ga4gh-io-schema/main/schemas/ga4gh-io-profile.schema.json",
  "$id": "https://your-domain.org/my-tool-schema.json"
}
```

### Converting existing schemas

The package also ships a converter that translates schemas from existing workflow ecosystems into GA4GH IO Profile schemas. Currently, Nextflow `nf-schema` files (`nextflow_schema.json`) are supported:

```bash
ga4gh-io-schema-converter --format nextflow --input nextflow_schema.json --output ga4gh_profile.schema.json
```

The Nextflow converter promotes the schema to JSON Schema Draft 2020-12, references the GA4GH meta-schema in `$schema`, moves all pipeline parameters under `properties.inputs`, maps `nf-schema` UI keywords to the `x-ga4gh-*` vocabulary (`fa_icon` → `x-ga4gh-fa-icon`, `hidden` → `x-ga4gh-hidden`, `errorMessage` → `x-ga4gh-error-message`), and strips engine directives that cannot be honoured in the cloud (`exists`). If `--output` is omitted, the result is printed to stdout.

Parsers are pluggable: support for further ecosystems is added by implementing `ga4gh_io_schema.parsers.AbstractParser` and registering it in `ga4gh_io_schema.parsers.PARSERS`.

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

- **Original Code & Schemas (`/src`, `/schemas`):** Licensed under **Apache-2.0**.
- **Documentation (`/docs`, `README.md`):** Licensed under **CC-BY-4.0**.

Please see the [`LICENSE`](LICENSE) file and `REUSE.toml` for complete details and mapping. Full license texts are located in the `/LICENSES` directory.

---

## Contacts

- **Maintainer:** ELIXIR On-Cloud / GA4GH Contributors
- **Repository:** [https://github.com/uniqueg/ga4gh-io-schema](https://github.com/uniqueg/ga4gh-io-schema)
