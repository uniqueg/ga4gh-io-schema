# Validator

The validator checks tool or workflow IO schemas against the GA4GH IO Profile
[meta-schema](../specification/meta-schema.md). It is available as a
command-line tool and as a Python API.

## Installation

To install the validator tool and all development dependencies for local testing, clone the repository and install it in editable mode:

```bash
git clone https://github.com/uniqueg/ga4gh-io-schema.git
cd ga4gh-io-schema
pip install -e ".[dev]"
```

## Command-line interface

Once installed, the package exposes a command-line interface to validate your drafted tool or workflow IO schemas against the GA4GH meta-schema:

```bash
ga4gh-io-schema-validator path/to/your-schema.json
```

Without further options, the meta-schema is the one that the schema names in
its `$schema` property (see [Referencing the
meta-schema](../specification/meta-schema.md#referencing-the-meta-schema)).
To validate against another meta-schema file, pass it with `--meta-schema`
(or `-m`):

```bash
ga4gh-io-schema-validator path/to/your-schema.json --meta-schema schemas/ga4gh-io-profile.schema.json
```

The command exits with status 0 if the schema complies with the profile, and
with status 1 and an error message otherwise.

## Python API

Reference of the Python API, generated from its docstrings.

::: ga4gh_io_schema.validator

::: ga4gh_io_schema.cli
