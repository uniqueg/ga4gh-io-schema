# CWL converter

The `convert cwl` subcommand of the [command-line interface](cli.md)
translates the inputs and outputs of a [CWL](https://www.commonwl.org/)
document into an IO schema. It reads `CommandLineTool`, `Workflow`,
`ExpressionTool` and `Operation` documents of CWL v1.0, v1.1 and v1.2, also
packed ones with a `$graph`, without evaluating JavaScript.

## Installation

The converter reads CWL with the parser of
[cwl-utils](https://github.com/common-workflow-language/cwl-utils), an optional
dependency. Install the package with the `cwl` extra, in the cloned repository
(see [Installation](validator.md#installation)):

```bash
pip install ".[cwl]"
```

Without it, `ga4gh-io-schema convert cwl` fails with exit status 3 and says
how to install it.

## Usage

```bash
ga4gh-io-schema convert cwl my-tool.cwl --output my-tool.schema.json
ga4gh-io-schema validate my-tool.schema.json
```

The IO schema goes to standard output, or to the file given with `--output`.
For a packed document with several processes, `--process` selects one by its
ID; the default is `main`, or the only process of the `$graph`:

```bash
ga4gh-io-schema convert cwl --process main packed-workflow.cwl
```

The converter checks its result against the profile before it writes it, so
the IO schema always complies (see [Validator](validator.md)). Relative
references (`$import`, `$include`) resolve against the directory of the
document, or the working directory for standard input (`-`).

### Warnings

What the profile can't express, or what would need JavaScript, is left out
of the IO schema and reported as a warning on standard error, with the JSON
path of the affected schema in the IO schema. The command still succeeds:

```text
Warning: Secondary file '.csi' is optional; the profile has only required secondary files, so it is left out. (at $.properties.inputs.properties.alignments)
```

With `--json`, the result is `{"output": "<IO schema>", "warnings": [...]}`,
with one object per warning, with its `message` and `location`. A CWL
document that isn't valid, or that has a type that can't be converted,
fails with exit status 1; a file that isn't UTF-8 text or valid YAML fails
with exit status 3 (see [Exit status](cli.md#exit-status)).

## Mapping

The process becomes the IO schema: its `label` the `title` and its `doc` the
`description`. Its inputs become the properties of `inputs`, and its outputs
the properties of `outputs`, with the IDs of the parameters as names:

| CWL | IO schema |
| ----- | ----- |
| `label`, `doc` (of a process, parameter, record field or type) | `title`, `description`; a `doc` given as a list of lines is joined with line breaks |
| `boolean`, `string` | `boolean`, `string` |
| `int`, `long` | `integer` |
| `float`, `double` | `number` |
| `File`, and `stdin`, `stdout`, `stderr` | file reference: `{"type": "string", "x-ga4gh-file": {"kind": "file"}}` (see [File references](../specification/files.md#mapping-to-workflow-languages)) |
| `Directory` | `{"type": "string", "x-ga4gh-file": {"kind": "directory"}}` |
| `format` (an IRI, or a namespaced name such as `edam:format_2572`) | `ontology` of the file reference, with the prefix expanded |
| `secondaryFiles` that are required (the default for inputs) | `secondaryFiles` of the file reference, with the patterns |
| `format` and `secondaryFiles` of a parameter with arrays or unions of files | on every file reference of the parameter, as in CWL |
| enum | `{"type": "string", "enum": [...]}`, with the symbols |
| array, e.g., `File[]` | `{"type": "array", "items": ...}` |
| record | `{"type": "object", "properties": ..., "required": [...], "additionalProperties": false}`, one property per field |
| union, e.g., `[File, string]` | `anyOf`, one branch per type |
| `null` in the type of a parameter or a record field, e.g., `File?` | not in `required`; elsewhere (e.g., in the items of an array), a `{"type": "null"}` branch |
| named types (`SchemaDefRequirement`, also with `$import`) | inlined where they are used |
| `default` | `default`; a file or directory becomes its location, if that is an absolute URI other than `file:` (e.g., `https:` or `s3:`) |
| an input with a `default` | not in `required` |
| `Any` | `{}` (any value), with a warning |

Inputs reject unknown properties (`"additionalProperties": false`), like the
[examples](../specification/examples.md) of the profile: a client sends only the
parameters of the tool. Outputs list the outputs that CWL requires a run to
produce in `required`.

## Limits

The converter leaves out, and reports:

- **Expressions.** A `format` or a secondary file pattern given as an
  expression (`$(...)` or `${...}`), or a `required` of a secondary file given
  as an expression.
- **Optional secondary files.** Patterns with `required: false`, or ending in
  `?`, and secondary files of outputs that aren't required explicitly (CWL
  makes them optional by default). The profile has only required secondary
  files.
- **Several formats.** A `format` with more than one term: `ontology` takes
  one.
- **Formats that aren't http(s) IRIs**, e.g., a namespaced name whose prefix
  is not declared in `$namespaces`.
- **Patterns that the profile doesn't accept**, e.g., with `/` (see [Secondary
  files](../specification/files.md#secondary-files)).
- **Default files that the IO schema can't refer to:** files next to the CWL
  document (relative locations, which the parser resolves to `file:` URIs) and
  file literals (`contents`). The input stays optional, as in CWL.
- **`Any`**, which becomes a schema that allows any value: values that are
  files aren't checked as file references.

These are errors, with exit status 1:

- **Recursive named types**, e.g., a record with a field of its own type: an
  IO schema has no references between its schemas.
- **Types that the document doesn't define**, e.g., a named type in a file
  that isn't imported, or on a remote server (see [Security](#security)).

The converter doesn't translate:

- **Bindings and requirements** (`inputBinding`, `outputBinding`,
  `requirements` other than `SchemaDefRequirement`): they say how a tool runs,
  not what its parameters are.
- **The output contract.** Outputs get their names, types, file references
  and `required`; the rules that tie them to the outputs of a run are not
  final yet ([#11](https://github.com/uniqueg/ga4gh-io-schema/issues/11)).

## Security

The converter reads the local files that a document imports (`$import`,
`$include`), as every CWL loader does: `$include` copies the content of any
local file that the user running the converter can read into the document,
and thus into the IO schema (e.g., into a `description`). Convert only
documents that you trust, or check the result before you publish it.

It never fetches remote resources: a document that imports a remote file
fails, and a workflow step that runs a remote tool is not read (only the
inputs and outputs of the converted process matter). Pack such documents
first (e.g., with `cwltool --pack`). It doesn't check that the files a
document refers to exist (e.g., default files).

## Relation to cwl-utils

`cwl-utils` has its own generator of JSON Schemas for CWL inputs,
`cwl-inputs-schema-gen`. It describes the CWL *job document*: files are
objects with `class` and `location`, and it leaves out `format`,
`secondaryFiles`, labels, defaults and outputs. An IO schema describes the
parameters for clients instead, with files as file references, so the
converter uses the parser of `cwl-utils` (which resolves the type
shorthands, namespaces, imports and packed documents) and maps the parsed
types itself.

## Python API

The converter can also be used from Python:

```python
from ga4gh_io_schema.cwl import CwlParser

parser = CwlParser()
schema = parser.to_ga4gh(parser.parse("my-tool.cwl"))
for note in parser.notes:
    print(note.location, note.message)
```

::: ga4gh_io_schema.cwl
    options:
      members:
        - CwlParser
        - ConversionNote
        - CwlConversionError
        - CwlSyntaxError
