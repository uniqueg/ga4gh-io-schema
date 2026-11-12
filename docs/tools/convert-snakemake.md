# Snakemake converter

Snakemake workflows validate their configuration with a JSON Schema
(`snakemake.utils.validate`, by convention
`workflow/schemas/config.schema.yaml`), and often their sample sheets with a
schema for one row (e.g., `workflow/schemas/samples.schema.yaml`). The
`convert snakemake` subcommand turns these schemas into an IO schema, so that
clients can render forms for the workflow and check its inputs.

## Installation

Snakemake schemas are usually YAML; reading YAML needs PyYAML, from the
`snakemake` extra (in a clone of the repository, see
[Installation](validator.md#installation)):

```bash
pip install ".[snakemake]"
```

JSON schemas need no extra. The `dev` extra includes PyYAML.

## Usage

```bash
ga4gh-io-schema convert snakemake workflow/schemas/config.schema.yaml \
  --sample-sheet workflow/schemas/samples.schema.yaml \
  --sample-sheet units=workflow/schemas/units.schema.yaml \
  --output workflow.io-schema.json
```

- The positional argument is the config schema, in YAML or JSON, or `-` for
  standard input.
- `--sample-sheet` (`-s`) adds the schema of the rows of a sample sheet, as
  `[PROPERTY=]PATH`: `PROPERTY` is the property of the configuration that
  holds the path of the sheet (a dotted path for nested properties, e.g.,
  `data.units`). Without it, the property is the one of `samples`,
  `sample_sheet`, `samplesheet` and `sample_table` that the config schema has
  at its top level; if it has none or several of them, name the property.
  Repeat the option for more sheets. A path that contains `=` but no
  property starts with `./`.
- `--file NAME`, `--directory NAME` and `--plain NAME` mark a property as a
  reference to a file or a directory, or keep it a plain string (see [File
  references](#file-references)). `NAME` is the dotted path of the property
  (e.g., `ref.fasta`), or the property of a sample sheet and a column (e.g.,
  `units.fq1`). Each option is repeatable.
- `--no-guess` turns the heuristics off: only the properties named with
  `--file`, `--directory` and `--sample-sheet` become file references.

The command checks the result against the profile before it writes it, and
fails (exit status 1) if the result doesn't comply, e.g., because the source
uses an `x-ga4gh-*` keyword wrongly. The shared options and the exit status
are those of all subcommands (see [Command-line interface](cli.md)).

### Notes

The converter reports what the author should check: every guessed file
reference, every dropped or kept keyword whose meaning changes, references
that the IO schema can't resolve, and the empty outputs. In text mode, notes
go to standard error, one per line, with the location in the IO schema:

```text
Note: Marked as a file reference (file): its name ends with 'fq'. Keep it a plain string with --plain units.fq1. (at $.properties.inputs.properties.units['x-ga4gh-tabular-schema'].items.properties.fq1)
```

With `--json`, the output is one object with the IO schema and the notes:
`{"schema": {…}, "notes": [{"message": "…", "location": "$.…"}]}`.

## Mapping

| Snakemake schema | IO schema |
| ----- | ----- |
| The config schema | `inputs`, with `"type": "object"` if the source doesn't set a type; `title`, `description` and the other keywords of the root stay with the inputs |
| `definitions` and `$defs` of the root of the config schema | `$defs` of the root of the IO schema |
| `$schema`, and `$id` (`id` in Draft 4) of a root | dropped: the IO schema names the profile, and the identifier names the source |
| Local references (`#/…`) | rewritten to the new location of their target (e.g., `#/properties/a` to `#/properties/inputs/properties/a`, `#/definitions/b` to `#/$defs/b`) |
| References to other documents (e.g., `units.schema.yaml`) | kept, with a note: the IO schema can't resolve them; include the referenced schema in the source first |
| Strings that look like paths (see [File references](#file-references)) | file references: `"x-ga4gh-file": {"kind": "file"}` or `{"kind": "directory"}`; `mediaType` `text/csv` or `text/tab-separated-values` if the default ends with `.csv` or `.tsv` |
| `format`, `contentMediaType`, `contentEncoding` and `contentSchema` of a file reference | dropped, with a note: file references can't have them (see [File references](../specification/files.md#the-annotation)) |
| A sample-sheet schema (one row) | `"x-ga4gh-tabular-schema": {"type": "array", "items": <row schema>}` of the property of the sheet, which becomes a file reference; this hint is experimental. Its columns get file references by the same rules; its local references point into the hint |
| Outputs | `"outputs": {"type": "object", "properties": {}}`, with a note: Snakemake schemas don't describe outputs; add them by hand |
| `x-ga4gh-*` keywords of the source | kept; the check of the result rejects wrong ones |

### Upgrade to Draft 2020-12

Snakemake reads schemas of any draft that `jsonschema` supports. The
converter reads the draft from `$schema` (with `http` or `https`, with or
without a trailing `#`); without `$schema`, or with an unknown one, it reads
Draft 2020-12, with a note. Draft 3 schemas are rejected.

| Source | Draft 2020-12 |
| ----- | ----- |
| `definitions` | `$defs` (an entry in both is an error) |
| `dependencies` | `dependentRequired` (lists of names) and `dependentSchemas` (schemas) |
| `items` with a list of schemas, `additionalItems` | `prefixItems`, `items`; `additionalItems` without a list in `items` has no effect and is dropped, with a note |
| `exclusiveMaximum: true` and `maximum` (Draft 4), and the same for the minimum | `exclusiveMaximum` with the value of `maximum`; `false` is dropped; `true` without a bound is dropped, with a note |
| `id` (Draft 4), and `$id` with only a fragment (Drafts 6 and 7) | `$anchor` for fragments (`#name`), `$id` otherwise |
| `$recursiveRef`, `$recursiveAnchor` (Draft 2019-09) | kept, with a note: Draft 2020-12 ignores them; replace them with `$dynamicRef` and `$dynamicAnchor` |

Schemas with their own identifier (`$id`, or `id` in Draft 4) inside the
source are embedded resources: their references are relative to that
identifier and are kept as they are.

## File references

Snakemake configurations are plain YAML: a path is a string like any other.
The converter marks a string property as a file reference (`x-ga4gh-file`)
if it holds a sample sheet, if an option names it, or if one of these rules
applies, tried in this order (names are split into words at `_`, `-`, `.` and
case changes, and trailing digits are ignored, so `fq1` ends with `fq`):

| Rule | Kind | Examples |
| ----- | ----- | ----- |
| The last word of the name ends with `dir`, or is `directory` or `folder` | directory | `outdir`, `tmp_dir`, `results_folder` |
| The last word of the name is a file word: `bam`, `bed`, `cram`, `csv`, `fa`, `fasta`, `fastq`, `file`, `fna`, `fq`, `gff`, `gtf`, `json`, `path`, `samplesheet`, `sheet`, `tsv`, `vcf`, `yaml`, `yml` | file | `genome_fasta`, `fq1`, `annotationGtf`, `bed_file` |
| The name is `samples`, `sample_sheet`, `samplesheet` or `sample_table` | file | `samples` |
| The default ends with `/` | directory | `"resources/"` |
| The default ends with a file extension (`.bam`, `.bed`, `.csv`, `.fa`, `.fasta`, `.fastq`, `.fq`, `.gtf`, `.gff`, `.json`, `.tsv`, `.txt`, `.vcf`, `.yaml`, indexes such as `.bai` and `.tbi`, and others), optionally compressed (`.gz`, `.bgz`, `.bz2`, `.xz`, `.zst`) | file | `"config/samples.tsv"`, `"ref.vcf.gz"` |
| The description says "path to", "path of", "URL to" or "URI of" | directory if it mentions a directory or folder and no file; file otherwise | "path to FASTQ file" |

Only schemas with `"type": "string"` and no in-place applicators (`allOf`,
`anyOf`, `oneOf`, `not`, `if`, `then`, `else`, `$ref`, `$dynamicRef`) can be
file references. Strings that a rule matches but that can't be file
references (e.g., `"type": ["string", "null"]`) stay as they are, with a
note; if an option names them, the conversion fails. Schemas that have an
`x-ga4gh-file` already are kept as they are.

The rules guess: check the notes, and correct them with the options.
Properties that the options can't name (e.g., in `$defs`, or in `allOf`) are
marked by the same rules, and the note says to edit the result if the guess
is wrong. The converter doesn't guess `compression`, `ontology`,
`secondaryFiles` or `schemes`; add them by hand where they help clients.

## Limits

- **Outputs:** Snakemake schemas describe the configuration only. The
  outputs of the workflow (e.g., from its `rule all`, or its report) must be
  added by hand.
- **Names:** the options name properties by dotted paths, reached through
  `properties` from the root of a schema; names that contain dots can't be
  told apart from nested properties.
- **Sample sheets:** the hint describes the rows as Snakemake validates them
  (one object per row, from a pandas data frame); how the workflow reads the
  sheet (e.g., separator, types of columns) isn't part of the schema. Values
  in sample sheets follow the rules of [File references in tabular
  files](../specification/files.md#file-references-in-tabular-files).
- **YAML:** schemas are read with PyYAML's safe loader, as Snakemake reads
  them, so YAML 1.1 rules apply (e.g., unquoted `yes` and `no` are
  booleans); dates stay strings. Documents with more than 100,000 values
  (e.g., through YAML aliases) are rejected.
- **Defaults:** `snakemake.utils.validate` can fill in defaults; the IO
  schema keeps them as `default`, which clients may prefill.

## Python API

::: ga4gh_io_schema.converters.snakemake
    options:
      show_root_heading: false
      members:
        - to_ga4gh
        - load_schema
        - SampleSheet
        - Conversion
        - Note
        - ConversionError
        - SourceError
