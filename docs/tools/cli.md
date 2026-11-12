# Command-line interface

The package installs one command, `ga4gh-io-schema`, with one subcommand per
tool:

| Subcommand | Purpose |
| --- | --- |
| `validate` | Check an IO schema against the GA4GH IO Profile (see [Validator](validator.md)). |
| `convert wdl` | Convert the inputs and outputs of a WDL workflow or task to an IO schema (see [WDL converter](wdl.md)). |

Further converters and the WES tools will be added as subcommands (e.g.,
`ga4gh-io-schema convert nextflow`). `ga4gh-io-schema --help` lists the
subcommands, and `ga4gh-io-schema <subcommand> --help` their options.

!!! note "Renamed in v0.3.0"
    `ga4gh-io-schema validate` replaces the `ga4gh-io-schema-validator`
    command of earlier versions, which is gone without an alias.

## Conventions

All subcommands share these conventions; the shared options (`--output`,
`--json`) go after the subcommand (`ga4gh-io-schema validate --json …`):

- **Input:** a path, or `-` to read from standard input (UTF-8, like
  files):

    ```bash
    cat my-tool.schema.json | ga4gh-io-schema validate -
    ```

- **Output:** the result goes to standard output, or to the file given with
  `--output` (`-o`; `-o -` is standard output). A failed command writes no
  output file.
- **Errors:** errors go to standard error, as one line of text:

    ```text
    Validation Error: 'inputs' is a required property (at $.properties)
    ```

- **JSON:** with `--json`, the result and the errors are JSON objects on one
  line. A command whose result is text (e.g., a converted file) writes
  `{"output": "<text>"}`. An error has a `kind` (`validation`, `io`, `meta-schema` or
  `internal`), a `message`, the JSON path of the offending value as
  `location` (or `null`), and the `exitCode`:

    ```json
    {"error": {"kind": "validation", "message": "'inputs' is a required property", "location": "$.properties"}, "exitCode": 1}
    ```

    `ga4gh-io-schema validate --json` writes
    `{"valid": true, "schema": "<path>", "metaSchema": null}` on success
    (`metaSchema` is the `--meta-schema` path, if given). Wrong arguments are
    reported by `argparse` as text, also with `--json`.

## Exit status

| Status | Meaning |
| --- | --- |
| 0 | Success (e.g., the schema complies). |
| 1 | The input doesn't comply (e.g., a validation error). |
| 2 | Wrong arguments, or no subcommand. |
| 3 | A file can't be read or written, or can't be used: it isn't UTF-8 text or valid JSON, is too deeply nested, or the meta-schema given with `--meta-schema` is malformed or has references that can't be resolved. |
| 4 | An unexpected error (please report it). |

## Reference

Generated from the argument parser when the documentation is built.

<!-- cli-reference -->
