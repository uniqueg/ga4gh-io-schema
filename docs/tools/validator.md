# Validator

The validator checks tool or workflow IO schemas against the GA4GH IO Profile
[meta-schema](../specification/meta-schema.md). It is available as a
command-line tool and as a Python API.

## Installation

To install the validator tool and all development dependencies for local testing, clone the repository and install it in editable mode:

```bash
git clone https://github.com/elixir-cloud-aai/ga4gh-io-schema.git
cd ga4gh-io-schema
pip install -e ".[dev]"
```

To install only the validator, run `pip install .` in the cloned repository
instead. The package supports Python 3.11 and later. It ships the meta-schema
and its vocabularies, so the validator works offline and outside the
repository. Its dependencies are jsonschema and referencing, and regress for
the [patterns of values](#patterns-of-values); the converters need the
extras `cwl`, `wdl` and `snakemake` (see [Converters](converters.md)).

## Command-line interface

Once installed, the `validate` subcommand of the
[command-line interface](cli.md) checks your drafted tool or workflow IO
schemas against the GA4GH meta-schema:

```bash
ga4gh-io-schema validate path/to/your-schema.json
```

Without further options, the validator always checks the schema against the
GA4GH IO Profile meta-schema that the package ships, whatever the schema's
`$schema` says. The schema's `$schema` must name that meta-schema by its
`$id` (see [Referencing the
meta-schema](../specification/meta-schema.md#referencing-the-meta-schema)); a
missing `$schema`, or one that names another meta-schema (e.g., plain JSON
Schema), is an error. To validate against another meta-schema file, pass it
with `--meta-schema` (or `-m`); if that meta-schema has an `$id`, the schema's
`$schema` must name it:

```bash
ga4gh-io-schema validate path/to/your-schema.json --meta-schema path/to/meta-schema.json
```

The command exits with status 0 if the schema complies with the profile, and
with status 1 and an error message on standard error if it doesn't (see
[Exit status](cli.md#exit-status) for the other cases). Validation errors
name the location of the offending keyword as a JSON path, for example:

```text
Validation Error: 'banana' is not valid under any of the given schemas (at $.properties.inputs.properties.sample_id['x-ga4gh-ui-widget'])
```

The schema can also come from standard input (`-`), and `--json` reports
the result and errors as JSON objects (see [Conventions](cli.md#conventions)).

## Format checks

The validator checks the `format` keywords of the meta-schema, for example
that `$id` is a URI reference and that `x-ga4gh-ontology` is a URI. It uses
the `format-nongpl` extra of `jsonschema`, which avoids GPL-licensed
dependencies. It checks the `regex` format of `pattern` and of the names in
`patternProperties` as ECMA-262 regular expressions in Unicode mode (the
`u` flag), with the engine that matches values (see [Patterns of
values](#patterns-of-values)), not with Python's `re`.

These checks apply to the IO schema itself, not to the input values that a
WES request sends later. File references don't use `"format": "uri"`, which
would reject DRS URIs with a compact identifier (`drs://prefix:accession`),
because the part after the colon isn't a port number; the meta-schema rejects
`format` on them. Their values follow the rules of [File
references](../specification/files.md#values).

## Patterns of values

Input and output values are matched with ECMA-262 semantics, as JavaScript
clients with Unicode-mode regular expressions (e.g., Ajv) match them:
`wes-params`, `wes-validate`, `outputs` and the [form proof of
concept](../adoption/form.md) match `pattern`, `patternProperties` and the
names that `additionalProperties` and `unevaluatedProperties` check with
[regress](https://github.com/Julian/regress), an ECMA-262 engine, in Unicode
mode. Where this differs from Python's `re`:

- `\p{L}` and other Unicode property escapes work.
- `$` doesn't match before a trailing newline: `^[a-z]+$` rejects
  `"abc\n"`, which `re` accepts.
- `\w`, `\d` and `\s` are as in ECMA-262: `\w` and `\d` match ASCII only
  (`^\w+$` rejects `"Zürich"`; use `\p{L}`).
- Escapes that Unicode mode doesn't allow are errors, e.g., `\-` outside a
  character class, `\_`, or `{,3}` as a quantifier.

A schema with a pattern that isn't valid in Unicode mode doesn't comply with
the profile: `validate` rejects it (the `regex` format), and so do the
subcommands that read a schema, before any value is matched.

## Python API

Reference of the Python API, generated from its docstrings.

::: ga4gh_io_schema.validator

::: ga4gh_io_schema.cli.base

::: ga4gh_io_schema.cli.app
