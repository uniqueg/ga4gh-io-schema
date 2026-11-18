# Converters

> Version 0.3.0 has converters from CWL, Nextflow, Snakemake and WDL (see
> [Roadmap](../roadmap.md#next-steps)). This page lists each of them; the
> available ones link to their pages.

## From workflow languages to IO schemas

- **Nextflow:** from `nextflow_schema.json` (nf-schema or nf-validation)
  and its sample-sheet schemas: `ga4gh-io-schema convert nextflow` (see
  [Nextflow converter](convert-nextflow.md)).
- **Snakemake:** from the config schema and the sample-sheet schemas; see
  [Snakemake converter](convert-snakemake.md).
- **CWL:** from the inputs and outputs of a `Workflow` or `CommandLineTool`;
  see [CWL converter](cwl.md).
- **WDL:** from `input`, `output` and `parameter_meta` blocks:
  `ga4gh-io-schema convert wdl` (see [WDL converter](convert-wdl.md)).

Converters emit only keywords and values of the profile version that they
target: output with removed ones (e.g., `x-ga4gh-fa-icon`, the `rst`
description format, the `password` widget) fails validation.

Every converter reports what the author should check (e.g., a guess, or a
part of the source that it left out) as notes, each with a message and the
location of the affected schema as a JSON path in the notation of the
validator (e.g., `$.properties.inputs.properties['call.threads']`). The
subcommands write the notes to standard error (`convert cwl` labels them
`Warning:`, the others `Note:`); with `--json`, the result holds them.

Converters mark every input and output that the source declares as a file
or a directory (or that may hold one) as a [file
reference](../specification/files.md), or fail with exit status 1: a
schema that leaves a file unmarked lets servers and clients accept any
string there, also `file:///etc/passwd` (see
[Security](../security.md#uris-and-file-references)). These cases fail:
the keys of a WDL `Map[File, V]` or `Map[Directory, V]`, CWL inputs and
outputs of type `Any`, and Nextflow parameters with a path `format` that
can't be a file reference (e.g., with `anyOf`) or with `format:
file-path-pattern` (a glob). `--allow-unmarked-files`
(`allow_unmarked_files=True` in the Python API) converts them to plain
schemas, with a note; the execution side must then
check their values itself. Guesses aren't declarations: the Snakemake
converter's notes on properties that look like files stay notes, and so do
the columns of sample sheets and the conditions `not` and `if` of the
Nextflow converter (see [File
references](convert-nextflow.md#file-references)).

## From IO schemas to WES

- **WES `workflow_params`:** build the `workflow_params` of a WES run request
  from values that are valid against an IO schema; available as
  [`wes-params`](wes-params.md).

## Python API: shared parts

The converter modules share the notes, the errors, the result of a
conversion, the file outputs given as options and the rendering of JSON
paths; each module also offers these under its own name (e.g.,
`ga4gh_io_schema.converters.wdl.Note`).

::: ga4gh_io_schema.converters.common
    options:
      show_root_heading: false

The converters of JSON Schema sources (Snakemake and nf-schema) share the
upgrade to Draft 2020-12, the rewriting of local references and the checks
of file references:

::: ga4gh_io_schema.converters.schemas
    options:
      show_root_heading: false
      members:
        - SchemaConverter
        - check_json
        - file_reference_problem
        - child_name
        - DATA_KEYWORDS
        - NOT_ON_FILES
