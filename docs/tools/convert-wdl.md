# WDL converter

`ga4gh-io-schema convert wdl` converts the inputs and outputs of a
[WDL](https://openwdl.org/) workflow, or of one of its tasks, to an IO
schema. It reads WDL 1.0, 1.1 and 1.2 documents, with their imports.

## Installation

The converter parses WDL with [miniwdl](https://github.com/chanzuckerberg/miniwdl),
an optional dependency of the `wdl` extra:

```bash
pip install ".[wdl]"
```

Without it, the command fails with exit status 3 and says how to install it.

## Usage

```bash
ga4gh-io-schema convert wdl workflows/variant_calling.wdl -o variant_calling.schema.json
ga4gh-io-schema validate variant_calling.schema.json
```

The IO schema goes to standard output (or to `--output`), and the notes of
the conversion go to standard error, one line each:

```text
Note: The default is an expression (basename(reads, ".bam")) that the engine evaluates; it is left out, and the input is optional (at $.properties.inputs.properties.sample_name)
```

With `--json`, the result is `{"schema": {…}, "notes": [{"message": …,
"location": …}]}`, and nothing goes to standard error. Notes report every
decision that changes the meaning of the schema or that the author should
check; read them before publishing the schema.

Options:

- `--task NAME` (`-t`): convert this task of a document without a
  workflow (e.g., a library of tasks). A document without a workflow and
  with a single task converts that task; with several tasks, `--task` is
  required. A document with a workflow converts the workflow, its [entry
  point](../specification/identity.md#entry-points); `--task` fails there.
- `--nested-inputs`: also include the optional inputs of calls that the
  workflow doesn't set, e.g., `align.threads` (see [Nested
  inputs](#nested-inputs)).
- `--import-path DIR` (`-p`, repeatable): a directory to search imports in
  and to read them from (see [Imports](#imports)).

A document that doesn't parse or type-check, has an unsupported version
or an import that isn't allowed, or can't be converted fails with exit
status 1 and the position of the first error; a document or an import that
can't be read (not found, not UTF-8) fails with exit status 3 (see [Exit
status](cli.md#exit-status)).

## Mapping

| WDL | IO schema |
| ----- | ----- |
| `String`, `Int`, `Float`, `Boolean` | `string`, `integer`, `number`, `boolean` |
| `File` | `{"type": "string", "x-ga4gh-file": {"kind": "file"}}` (see [File references](../specification/files.md)) |
| `Directory` (WDL 1.2) | `{"type": "string", "x-ga4gh-file": {"kind": "directory"}}` |
| `Array[T]`, `Array[T]+` | `array` with `items`; `+` adds `minItems: 1` |
| `Map[String, V]` | `object` with `additionalProperties` |
| `Map[File, V]` | as `Map[String, V]`, with a note: object keys can't be file references |
| `Pair[L, R]` | `object` with the required properties `left` and `right`, as engines read pairs from JSON |
| struct | `object` with the members as properties, the members that aren't optional in `required`, `additionalProperties: false`; WDL 1.2 `meta` (`description`) and `parameter_meta` of the struct describe the object and its members |
| `T?` (an optional input or output) | not in `required` |
| `T?` (a value inside an array, map, pair or struct of an input) | also accepts `null`: `"type": [T, "null"]`, or `anyOf` with `{"type": "null"}` for file references, whose type must be `string` |
| `T?` (an item of a list of an output) | as `T`: normalisers drop the `null` items of lists (see [Outputs](#outputs)) |
| `T?` (a value inside a map, pair or struct of an output) | also accepts `null`, as for inputs |
| input without default, not optional | in `required` |
| literal default (e.g., `= 4`, `= ["a"]`, `= {"k": 1}`) | `default` |
| literal default that isn't valid against the schema (e.g., `String s = 1`, which WDL coerces, or a value outside `choices`) | left out, with a note |
| default that is an expression (e.g., `= name + ".bam"`) | left out, with a note; the input is optional |
| default of a `File` or `Directory` that is a path (e.g., `= "data/ref.fa"`) | left out, with a note: the engine resolves the path on the execution side, while a path in an IO schema refers to a file attached to the run request; a default that is a URI with `//` after the scheme (e.g., `https://…`, `s3://…`, `drs://…`) is kept; other values with a colon (e.g., `C:/ref.fa`) are paths |
| default of a compound type that has strings in places of files (e.g., `Array[File] = ["a.txt"]`, or the keys of `Map[File, Int] = {"a.txt": 1}`) | left out, with a note |
| `meta` of the workflow or task: `description` | `description` of the IO schema; the name of the workflow or task is the `title` |
| workflow or task name | `entry_point` of [`x-ga4gh-workflow`](../specification/identity.md#the-workflow-block), with `descriptor_type: WDL`, the WDL version as `descriptor_type_version`, and the SHA-256 checksum of the bytes of the document |
| declared type (e.g., `Array[File]+`) | `type` of [`x-ga4gh-parameter`](../specification/identity.md#parameter-bindings) |

A workflow or task without an input section (allowed by engines for WDL
1.0) has as inputs its declarations that clients may set, with a note.

Inputs are named as in the input section of the workflow (e.g., `sample`),
not qualified with the workflow name (`variant_calling.sample`): the entry
point in `x-ga4gh-workflow` qualifies them when a client builds the
`workflow_params` of a WES request. The input section rejects inputs that
it doesn't list (`additionalProperties: false`), as engines do.

### `parameter_meta`

WDL defines no keys for `parameter_meta`. The converter maps the keys that
are in common use (e.g., in [BioWDL](https://biowdl.github.io/) and on
DNAnexus), for inputs and outputs:

| `parameter_meta` | IO schema |
| ----- | ----- |
| a string | `description` |
| `description`, `help` | `description`; both, separated by an empty line, if both are given |
| `label` | `title` |
| `category: "advanced"` | `x-ga4gh-hidden: true`; other categories are ignored |
| `choices` (inputs of primitive types) | `enum`, if the values are of the type of the input |
| `suggestions` (inputs of primitive types) | `examples`, likewise |

Other keys (e.g., `patterns`, `localization_optional`), `choices` and
`suggestions` of files, outputs or values of another type, and entries that
are neither strings nor objects are dropped with a note.

### Nested inputs

Engines let clients set the inputs of calls that a workflow doesn't set,
named with the call (e.g., `align.threads` for the input `threads` of the
call `align`); WDL 1.1 allows this only if the `meta` section of the
workflow sets `allowNestedInputs: true`, and WDL 1.2 only if its `hints`
section sets `allow_nested_inputs: true`. The converter includes:

- the required inputs of calls that the workflow doesn't set, always: the
  workflow can't run without them; they are in `required`, with a note;
- the optional inputs of calls, with `--nested-inputs` only, as hidden
  parameters (`x-ga4gh-hidden: true`), described by the `parameter_meta` of
  the called task or workflow.

The names of nested inputs are the property names (e.g.,
`"align.threads"`), so `x-ga4gh-parameter` needs no `name`. For a WDL 1.1
workflow without `allowNestedInputs: true`, the converter notes that engines
reject nested inputs; for WDL 1.2, it notes that `hints` must allow them,
as miniwdl doesn't expose the `hints` section to check it.

### Outputs

Every output of the output section becomes a property of `outputs`,
named as in the output section, with its type, description and
`x-ga4gh-parameter`, following [Outputs](../specification/outputs.md):

- outputs that aren't optional are in `required`: every run that completes
  produces them; `additionalProperties: false` says that a normalised
  outputs object has no other keys;
- outputs, and the items of their lists, don't allow `null`
  (`Array[File?]` becomes an array of file references): normalisers leave
  out the `null` values that engines report for optional outputs that a
  run didn't produce, and the `null` items of lists; optional values inside
  maps, pairs and structs still accept `null`, as normalisers keep them;
- `Map[String, File]` becomes files keyed by name, structs records;
- outputs have no defaults, and no `x-ga4gh-output-glob`: engines report
  WDL outputs by name, qualified with the workflow name (e.g.,
  `variant_calling.vcf`), which is how normalisers find them (see [Notes on
  engines and servers](../specification/outputs.md#notes-on-engines-and-servers)).

## Imports

Imports are resolved against the directory of the importing document, then
against the `--import-path` directories. For safety, the converter reads
imports only from local files below the directory of the document or one of
the `--import-path` directories:

- an import outside them (e.g., `../tasks/align.wdl`, or an absolute path)
  fails until its directory, or a directory above it, is given with
  `--import-path` (e.g., the root of the repository);
- `file://` imports are local files, with the same rule;
- remote imports (`https://…`) fail: the converter doesn't fetch URLs, so a
  registry can run it on documents that it doesn't trust; download them and
  import them from local files.

A document from standard input (`-`) resolves its relative imports against
the current directory, which is then the directory that imports may be read
from (besides the `--import-path` directories): run the converter in the
directory of the document, not, e.g., in `/`.

## Limits

- WDL draft-2 documents (without a `version` line) are rejected.
- WDL has no secondary files: index files are separate inputs and become
  separate file references. Media types, format terms and compression of
  files aren't known from WDL types; add them to the IO schema by hand (or
  in a later version of the converter, from `parameter_meta`).
- Defaults that are expressions are left out (see [Mapping](#mapping)); the
  converter never evaluates expressions, so a document can't make it read
  files or call functions.
- The keys of maps are plain strings, also for `Map[File, V]`.
- The converter doesn't set `$id`, the TRS identifiers or
  `primary_descriptor_path` of `x-ga4gh-workflow`; add them when the
  workflow is published (see [Identity and engine
  binding](../specification/identity.md)).
- The checksum covers the bytes of the converted document only (for
  standard input and other pipes, its text in UTF-8); changes of imported documents aren't
  detected (see
  [Drift](../specification/identity.md#drift)).
- Translating input values to the `workflow_params` of a WES request, and
  normalising the outputs of a run, isn't part of the converter.

## Python API

The module also offers the [shared parts of the
converters](converters.md#python-api-shared-parts) under its name:
`Conversion`, `Note`, `SourceError`, `ConversionError` and `json_path`.

::: ga4gh_io_schema.converters.wdl
