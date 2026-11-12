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

To install only the validator, run `pip install .` in the cloned repository
instead. The package supports Python 3.11 and later. It ships the meta-schema
and its vocabularies, so the validator works offline and outside the
repository.

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

## Format checks

The validator checks the `format` keywords of the meta-schema, for example
that `$id` is a URI reference and that `x-ga4gh-ontology` is a URI. It uses
the `format-nongpl` extra of `jsonschema`, which avoids GPL-licensed
dependencies. It doesn't check the `regex` format of `pattern` keywords,
because patterns are ECMA-262 regular expressions, which Python can't always
parse (e.g., `\p{L}`).

A `$schema` that the package doesn't ship, for example the earlier
unversioned URL with `main` in its path, is reported as an unknown
meta-schema; use the versioned URL (see [Referencing the
meta-schema](../specification/meta-schema.md#referencing-the-meta-schema)).

These checks apply to the IO schema itself, not to the input values that a
WES request sends later. If a client also checks those values against
`"format": "uri"`, note that DRS URIs with a host name
(`drs://drs.example.org/314159`) are valid URIs, but DRS URIs with a compact
identifier (`drs://drs.example.org:314159` or `drs://prefix:accession`) are
not, because the part after the colon isn't a port number.

## Python API

Reference of the Python API, generated from its docstrings.

::: ga4gh_io_schema.validator

::: ga4gh_io_schema.cli
