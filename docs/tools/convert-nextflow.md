# Nextflow converter

Nextflow pipelines describe their parameters with a JSON Schema,
`nextflow_schema.json`, which the
[nf-schema](https://nextflow-io.github.io/nf-schema/latest/nextflow_schema/nextflow_schema_specification/)
plugin checks before a run (Draft 2020-12; its predecessor nf-validation
used Draft 7). nf-core pipelines and Seqera Platform build their launch
forms from it. The `convert nextflow` subcommand turns it into an IO schema,
so that any client can render forms for the pipeline and check its inputs.

## Usage

```bash
ga4gh-io-schema convert nextflow nextflow_schema.json \
  --directory star_index \
  --out-file report=multiqc/multiqc_report.html \
  --output pipeline.io-schema.json
```

- The positional argument is the nf-schema file, or `-` for standard input.
  It needs no extra: nf-schema files are JSON.
- `--pipeline-dir DIR`: the directory of the pipeline. The command reads the
  sample-sheet schemas that the source names with `schema` (e.g.,
  `assets/schema_input.json`) relative to it, as nf-schema does. By default,
  it's the directory of the nf-schema file, or the working directory for
  standard input. A schema that isn't there is left out, with a note; a path
  that leads out of the directory is an error.
- `--directory NAME` marks the parameter `NAME` with `format: path` (a file
  or a directory) as a reference to a directory; without it, it's a file
  (see [File references](#file-references)). Repeatable.
- `--out-file NAME=GLOB`, `--out-files NAME=GLOB` and `--out-dir NAME=GLOB`
  add the output `NAME`: a file, a list of files or a directory, found by
  `x-ga4gh-output-glob` among the files of the run, relative to the output
  directory of the pipeline (`outdir`; see [Outputs](#outputs)). Each
  option is repeatable; the outputs keep the order of the options. Quote
  globs in the shell.

The command checks the result against the profile before it writes it, and
fails (exit status 1) if the result doesn't comply (e.g., because the source
uses an `x-ga4gh-*` keyword wrongly), or if the source can't be converted
(e.g., it isn't an object, or `--directory` names a parameter without
`format: path`). A source or sample-sheet schema that can't be read
(invalid JSON, values that JSON can't represent such as `NaN`, too deeply
nested, outside the directory of the pipeline) exits with status 3. The
shared options and the exit status are those of all subcommands (see
[Command-line interface](cli.md)).

### Notes

The converter reports what the author should check: guesses (`format:
path`), keywords that it drops or keeps although their meaning changes,
sample sheets that it didn't find, references that the IO schema can't
resolve, and the empty outputs. Keywords that nf-core pipelines use on many
parameters (`fa_icon`, `exists`, `meta`, and `pattern` on file references)
get one note each, at their first place, with the number of other places.
In text mode, notes go to standard error, one per line:

```text
Note: Marked as a file reference (file): 'format: path' is a file or a directory; if it's a directory, name it with --directory salmon_index. (at $['$defs'].reference_genome_options.properties.salmon_index)
```

With `--json`, the output is one object with the IO schema and the notes:
`{"schema": {…}, "notes": [{"message": "…", "location": "$.…"}]}`.

## Mapping

| nf-schema | IO schema |
| ----- | ----- |
| The nf-schema file | `inputs`, with `"type": "object"` if the source doesn't set a type; `title`, `description`, `allOf` and the other keywords of the root stay with the inputs |
| Groups of parameters (`$defs`, or `definitions` of nf-validation), referenced from `allOf` | `$defs` of the root of the IO schema, still referenced from `allOf` of `inputs`; their `title`, `description` and `required` stay. Clients that follow `$ref` and `allOf` (as [`wes-params`](wes-params.md) does) see the parameters of all groups |
| `$schema`, and `$id` of the root | dropped: the IO schema names the profile, and the identifier names the source |
| `"format": "file-path"` | `"x-ga4gh-file": {"kind": "file"}`, without `format` |
| `"format": "directory-path"` | `"x-ga4gh-file": {"kind": "directory"}`, without `format` |
| `"format": "path"` (a file or a directory) | `"x-ga4gh-file": {"kind": "file"}`, with a note; `{"kind": "directory"}` if `--directory` names the parameter |
| `"format": "file-path-pattern"` (a glob) | a plain string, without `format`, with a note: a glob isn't a reference to one file |
| `mimetype` | `mediaType` of the file reference, if it's a media type (e.g., `text/csv`); dropped with a note otherwise, and on directories |
| `schema` (the path of a sample-sheet schema) | `x-ga4gh-tabular-schema` of the file reference: the converted schema of the whole sheet (an array of rows), an experimental hint for clients (see [Keywords](../specification/keywords.md#tabular-data-and-cloud-sovereignty)); its columns get file references by the same rules. Dropped with a note on directories, in sample sheets, and if the schema isn't found |
| `pattern` | `pattern`, unchanged (it constrains the value); on file references, one note (see [Limits](#limits)) |
| `help_text` | appended to `description` after a blank line, with `"x-ga4gh-description-format": "markdown"` (unless the source sets a format) |
| `hidden` | `x-ga4gh-hidden` |
| `errorMessage` (a string) | `x-ga4gh-error-message`; an object of messages per keyword is dropped, with a note |
| `fa_icon` | dropped: the profile has no icon keyword since version 0.3 (see [Roadmap](../roadmap.md#cut)) |
| `exists` | dropped: Nextflow checks it where the pipeline runs, on the paths that the pipeline sees, and skips it for object-store paths; the profile leaves such checks to the engine (see [Rationale](../rationale.md)) |
| `meta` (of sample-sheet columns) | dropped: it maps a column to the meta map of the pipeline's channels, which is part of the pipeline, not of its inputs |
| `uniqueEntries` (nf-schema), `unique` (nf-validation) | dropped, with a note: they require the combination of some columns to be unique across the rows, which `uniqueItems` doesn't express (see [Keywords](../specification/keywords.md#leveraging-native-json-schema-what-we-dont-reinvent)) |
| `format`, `contentMediaType`, `contentEncoding` and `contentSchema` of a file reference | dropped (the last three with a note): file references can't have them (see [File references](../specification/files.md#the-annotation)) |
| Outputs | the outputs named with `--out-file`, `--out-files` and `--out-dir` (see [Outputs](#outputs)); without them, `"outputs": {"type": "object", "properties": {}}`, with a note |
| The pipeline | `"x-ga4gh-workflow": {"descriptor_type": "NFL"}` (see [Identity and engine binding](../specification/identity.md#the-workflow-block)); add an `$id`, and the TRS ids, the path and the checksum of `main.nf` when the pipeline is published. Parameters keep their names, so no `x-ga4gh-parameter` is needed |
| `x-ga4gh-*` keywords of the source | kept; the check of the result rejects wrong ones. If a schema has both an nf-schema keyword and its keyword of the profile (e.g., `hidden` and `x-ga4gh-hidden`), the latter wins, with a note |

The converter upgrades the schemas to Draft 2020-12 as the [Snakemake
converter](convert-snakemake.md#upgrade-to-draft-2020-12) does, with the
same code: it reads the draft from `$schema` (Draft 7 for nf-validation,
Draft 2020-12 for nf-schema; other drafts from 4 on), rewrites `definitions`
to `$defs` and local references to the new places of their targets (e.g.,
`#/definitions/input_output_options` to `#/$defs/input_output_options`, and
references in a sample-sheet schema to its place in the hint), and reports
references that point to nothing.

## File references

nf-schema marks paths with `format`, so the converter doesn't guess: only
schemas with `"format": "file-path"`, `"directory-path"` or `"path"` become
file references. A file reference must be a flat string schema (`"type":
"string"`, no in-place applicators such as `anyOf`); a schema with a path
format that can't be one (e.g., `"type": ["string", "null"]`) keeps its
`format`, with a note, and loses `mimetype` and `schema`. A schema that has an
`x-ga4gh-file` already is kept as it is.

`format: path` means a file or a directory. nf-core uses it for indexes that
are a directory or an archive (e.g., `star_index`). The converter marks it as
a file, and the note names the option that makes it a directory; parameters
in sample sheets can't be named, so edit the result there.

`outdir` (`format: directory-path` in nf-core pipelines) becomes a directory
reference like any other: the client or the deployment sets it to where the
results go (see [Outputs](#outputs)).

## Outputs

`nextflow_schema.json` describes parameters only. Nextflow's typed workflow
outputs (stable since Nextflow 25.10) are declared in the pipeline code, and
WES servers don't report them by name, so clients find them by glob among
the files of the run, relative to the output directory (see [Notes on
engines and servers](../specification/outputs.md#notes-on-engines-and-servers)).
The output options name them, as for the Snakemake converter:

| Option | Output schema |
| ----- | ----- |
| `--out-file NAME=GLOB` | `{"type": "string", "x-ga4gh-file": {"kind": "file"}, "x-ga4gh-output-glob": GLOB}` |
| `--out-files NAME=GLOB` | `{"type": "array", "items": {"type": "string", "x-ga4gh-file": {"kind": "file"}}, "x-ga4gh-output-glob": GLOB}` |
| `--out-dir NAME=GLOB` | `{"type": "string", "x-ga4gh-file": {"kind": "directory"}, "x-ga4gh-output-glob": GLOB}` |

The glob is relative to the output directory, with the syntax of
[`x-ga4gh-output-glob`](../specification/outputs.md#x-ga4gh-output-glob)
(e.g., no absolute paths, `..` or braces); the check of the result rejects
other globs. The draft [pipeline spec](../related-work.md#nextflow-pipeline-spec-6900)
of Nextflow adds outputs; a later version of the converter can read them
from it once it's adopted.

## Limits

- **Patterns of file references:** nf-core pipelines constrain paths with
  `pattern` (e.g., `^\S+\.csv$`). The pattern applies to the value of the
  file reference, so values whose last part isn't the file name (e.g., DRS
  identifiers such as `drs://drs.example.org/314159`) fail it. The converter
  keeps it, as the specification asks, and the note lists where; remove it
  where such values must work.
- **Sample sheets:** the hint describes the sheet as nf-schema validates it
  (an array of rows); how the pipeline reads the sheet (e.g., CSV, TSV or
  YAML) isn't part of the schema. Values in sample sheets follow the rules
  of [File references in tabular
  files](../specification/files.md#file-references-in-tabular-files). A
  sample-sheet schema is converted once per parameter that names it.
- **Descriptions:** with `help_text`, the whole description is Markdown,
  including the short description, which is plain text in nf-schema;
  characters that Markdown reads (e.g., `*` or `_`) may render differently.
- **Groups:** clients that render forms see the groups as `allOf` branches
  with a `title` and a `description`; the profile has no keyword for
  sections of a form.
- **Entry points and profiles:** Nextflow's `-entry` and `-profile` aren't
  parameters and aren't part of the schema (see [Engine
  bindings](../specification/engine-bindings.md#nextflow-nfl)).

## Python API

::: ga4gh_io_schema.converters.nextflow
    options:
      show_root_heading: false
      members:
        - to_ga4gh
        - load_schema
        - sample_sheet_paths
        - FILE_FORMATS
        - DROPPED
        - Output
