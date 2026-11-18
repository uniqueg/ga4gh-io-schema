# Engine bindings

An IO schema describes input *values*: a JSON object that is valid against
the schema's `inputs`. A GA4GH Workflow Execution Service (WES) receives
`workflow_params`, whose shape depends on the engine: Nextflow and Snakemake
take flat parameters or a configuration object, WDL takes names qualified
with the workflow, CWL takes `File` and `Directory` objects. This page
defines, for each descriptor type, how input values become `workflow_params`
and which fields of the WES `RunRequest` come from the Tool Registry Service
(TRS). It is normative for request builders and for WES servers that
validate requests (see [Conformance](conformance.md)).

Requirements on this page use the key words of BCP 14, as described in
[Notational conventions](conformance.md#notational-conventions).

The translation uses the [workflow block](identity.md#the-workflow-block)
(`descriptor_type`, `descriptor_type_version`, `entry_point`), the
[parameter bindings](identity.md#parameter-bindings) (`x-ga4gh-parameter`)
and the [file references](files.md) (`x-ga4gh-file`) of the schema. No
change of WES is needed: the result is an ordinary WES 1.1 run request.

## From input values to `workflow_params`

These rules apply to every descriptor type; the next section adds what
differs between them.

1. **Validation first.** A request builder MUST validate the input values
   against `inputs` (with the schema's references resolved locally, see
   [Sources of schemas](../security.md#sources-of-schemas)), and every value
   of a file reference against the rules of [Values](files.md#values) and the
   deployment's allow-list of schemes, before it translates them. It MUST
   NOT translate or submit values that fail.
2. **Names.** Each property of the input values becomes one member of
   `workflow_params`. Its key is the `name` of the property's
   `x-ga4gh-parameter`, or else the name of the property, qualified as the
   descriptor type requires (see [Bindings per descriptor
   type](#bindings-per-descriptor-type)). Names are used verbatim: a dot in
   a name has no meaning, except where the descriptor type gives it one.
   `x-ga4gh-parameter` renames only the properties of `inputs`; members of
   nested objects keep their names. Two inputs MUST NOT bind to the same
   key (for `NFL`, to keys with the same Nextflow name, see
   [Nextflow](#nextflow-nfl)); a translator MUST reject values for which
   they would. The keys of objects in the values MUST be strings, as in
   JSON.
3. **Absent and optional values.** An input without a value is left out of
   `workflow_params`, and the engine applies the workflow's own default. A
   translator MUST NOT insert the schema's `default`s: the default of the
   descriptor is authoritative, and the schema's `default` is for forms (a
   form that prefills it sends it as a value). `null` is passed unchanged
   where the schema allows it; clients SHOULD leave out unset inputs rather
   than send `null`.
4. **Other values.** Strings, numbers, booleans, arrays and objects that
   aren't file references are passed unchanged, at every depth (e.g., WDL
   structs, maps and pairs, CWL records, Snakemake configuration sections).
   `x-ga4gh-parameter.type` is informative; it doesn't change the value.
   For `CWL`, a translator MUST reject objects with the `class` `File` or
   `Directory` in the input values, at any depth: the runner would stage
   them without the checks of file references. Files are given as file
   reference values, i.e., strings. For `CWL`, a translator MUST also
   reject object keys that start with `$` or contain `:`, at any depth and
   among the members of the input values. The CWL loader (schema-salad)
   takes keys with `$` for directives: `$include` and `$import` make it
   read or fetch the document they name (also `file:` URIs and internal
   hosts) past the checks of file references, and `$mixin`, `$namespaces`
   and `$schemas` change the values. Keys with `:` are namespaced fields or
   URIs, which cwltool expands and applies, e.g., `cwltool:overrides` and
   `cwl:requirements` (requirements such as another container image). The
   ids of CWL inputs and record fields have neither. Errors name the
   location of the key, not its value.
5. **File references.** A string value is a file value if a file reference
   schema applies at its location: directly; in the `items`,
   `prefixItems` or `contains` of an array; in the `properties`,
   `patternProperties` or `additionalProperties` of an object; in
   `unevaluatedItems` or `unevaluatedProperties`, for items and members
   that no other keyword evaluates; in the `dependentSchemas` of the
   members that an object has; through `$ref`, `allOf`, or `if` with `then`
   or `else`; or as a branch of `anyOf` or `oneOf` that the value is valid
   against, even if a plain string branch next to it would accept the value
   too (see [Values](files.md#values)). A translator MUST reject schemas
   whose applicators it doesn't model (e.g., `$dynamicRef`) rather than skip
   the values under them. If several file references apply to one value,
   the value MUST meet all of them (e.g., the `schemes` of each), and they
   MUST have the same `kind`; a union of a file and a directory (e.g., CWL
   `[File, Directory]`) therefore can't be expressed in version 0.3.0, because
   every string is valid against both. File values are passed as their
   descriptor type requires.
   Secondary files are not sent: the execution side finds them next to the
   referenced file (see [Secondary files](files.md#secondary-files)).

## Bindings per descriptor type

| Descriptor type | Keys of `workflow_params` | File values | Entry point |
| ----- | ----- | ----- | ----- |
| `NFL` | The name, unqualified | The string, unchanged | Not part of `workflow_params` |
| `SMK` | The name, unqualified | The string, unchanged | Not used |
| `WDL` | `<entry_point>.<name>` | The string, unchanged | Qualifies every key |
| `CWL` | The name (the input id, without `#` or the process id) | `{"class": "File", "location": …}` or `{"class": "Directory", "location": …}` | Fragment of `workflow_url` |
| `GALAXY` | Not defined in version 0.3.0 | | |

### Nextflow (`NFL`)

`workflow_params` is the object of pipeline parameters, as in a Nextflow
params file (`-params-file`): each input is a member, under its name,
with its value; file values are the strings themselves (URIs or paths), which
Nextflow stages. For example:

```json
{
  "reads": "drs://drs.example.org/314159",
  "genome_index": "https://data.example.org/index/",
  "sample_names": ["s1", "s2"],
  "skip_qc": false
}
```

Nextflow renames the members of a params file whose keys contain `-`
(U+002D) from kebab-case to camelCase: it splits the key at each `-`,
drops the empty parts at the end and capitalises the first character of
each part but the first (`out-dir` and `out-dir-` set `outDir`, `-input`
sets `Input`). The *Nextflow name* of a key is the name that Nextflow
gives it so; other dashes (e.g., U+2010) aren't renamed. Two keys with the
same Nextflow name set the same parameter, and the last one wins. So, for
`NFL`, translators and servers compare keys by their Nextflow names (rule
2 above and rule 1 of "From `workflow_params` back to input values"), and
MUST reject keys in which a character other than ASCII follows a `-`,
whose Nextflow name depends on how Java capitalises it. Keys keep their
form in `workflow_params`.

The `entry_point` of a Nextflow schema (the named workflow run with
`-entry`) is not a parameter. WES 1.1 has no field for it, and version 0.3.0
of the profile doesn't define one; a deployment that runs named workflows
documents how it takes the entry point (e.g., in
`workflow_engine_parameters`).

### Snakemake (`SMK`)

`workflow_params` is the Snakemake configuration object, as in a
configuration file (`--configfile`): each input is a top-level key of the
configuration. Nested sections of the configuration are inputs with object
values, passed unchanged; file values are the strings themselves.

```json
{
  "reference": { "fasta": "https://data.example.org/ref.fa", "name": "GRCh38" },
  "samples": [{ "id": "a", "bam": "drs://drs.example.org/a" }],
  "threads": 8
}
```

### WDL (`WDL`)

`workflow_params` is a WDL input file (the inputs JSON of WDL 1.x): each key
is the name of the input qualified with the entry point, `<entry_point>.<name>`,
where the name can itself be qualified with a call (`x-ga4gh-parameter.name`
`call_variants.threads` gives `variant_calling.call_variants.threads`).
`entry_point` is required for WDL. Values take the JSON form of WDL inputs:
`File` and `Directory` values are strings, `Array` values arrays, and `Pair`
(`{"left": …, "right": …}`), `Map` and struct values objects. For the inputs
of [Example 3](examples.md#example-3-workflow-bound-to-an-engine):

```json
{
  "variant_calling.input_bam": "https://data.example.org/sample.bam",
  "variant_calling.sample_names": ["NA12878"],
  "variant_calling.call_variants.threads": 8
}
```

### CWL (`CWL`)

`workflow_params` is a CWL input object (job order): each key is the id of
an input parameter of the process, without `#` and without the process
id. Every file value becomes a `File` object, or a `Directory` object for a
file reference of `kind` `directory`, with the value as its `location` and no
other fields; the CWL runner discovers secondary files and other attributes
(e.g., `basename`) from the location. Arrays of file references become
arrays of such objects, and file references in records become objects in the
record.

```json
{
  "reads": { "class": "File", "location": "https://data.example.org/sample.bam" },
  "index": { "class": "Directory", "location": "drs://drs.example.org/index" },
  "fastqs": [
    { "class": "File", "location": "inputs/r1.fq.gz" },
    { "class": "File", "location": "inputs/r2.fq.gz" }
  ]
}
```

The `entry_point` of a CWL schema (the process in a document with several,
e.g., `#main` in a packed document) is not part of `workflow_params`; it is
the fragment of `workflow_url` (see [Run requests](#run-requests)).

### Galaxy (`GALAXY`)

Version 0.3.0 defines no binding for Galaxy workflows; translators MUST reject
schemas with the descriptor type `GALAXY`.

## Run requests

A WES `RunRequest` gets these fields from the schema and from TRS:

| Field | Value |
| ----- | ----- |
| `workflow_params` | The translated input values (see above). |
| `workflow_type` | `descriptor_type` of the workflow block, which is the TRS descriptor type. |
| `workflow_type_version` | `descriptor_type_version` of the workflow block; if the schema has none, one of the `descriptor_type_version` values of the TRS tool version for the descriptor type. If the schema has one, a request builder MUST use it. |
| `workflow_url` | A URL from which the WES server gets the workflow, as the deployment accepts it: typically the plain primary descriptor of the TRS tool version that `trs_tool_id` and `trs_version_id` name, by its path (see [Workflow URLs in TRS](#workflow-urls-in-trs)). For `CWL` with an `entry_point`, the entry point is the fragment of the URL (e.g., `…/descriptor/align.cwl#main`); a URL that already has a fragment can't take one. |
| `workflow_attachment` | The files that relative paths in the input values refer to (see [Values](files.md#values)), if any. |

The binding doesn't set `tags`, `workflow_engine`,
`workflow_engine_version` or `workflow_engine_parameters`; they are choices
of the user or the deployment. A WES 1.1 run request is sent as
`multipart/form-data`, in which `workflow_params` (like `tags` and
`workflow_engine_parameters`) is a JSON-encoded string.

### Workflow URLs in TRS

A request builder that takes the `workflow_url` from TRS SHOULD use the
plain primary descriptor by its path:

```text
{trs}/tools/{id}/versions/{version_id}/PLAIN_{descriptor_type}/descriptor/{path}
```

`{path}` is the path of the primary descriptor exactly as TRS lists it
(`ToolFile.path` of the `PRIMARY_DESCRIPTOR` in
`GET .../{descriptor_type}/files`). TRS takes the paths that `/files` lists
as `{relative_path}`, so only a listed path is sure to be served. The
`primary_descriptor_path` of the workflow block SHOULD be that same path
(see [Identity](identity.md)); a request builder that can read `/files`
SHOULD prefer the listed path. The ids are percent-encoded as path
segments; the path keeps its `/` separators and has each segment
percent-encoded. A path with empty, `.` or `..` segments MUST NOT be used:
it would change where relative references resolve. A request builder that
reads `/files` SHOULD use the listed path with its empty and `.` segments
removed instead (e.g., `main.wdl` for `./main.wdl`, as clients compare
paths, see [Matching file entries](../adoption/trs.md#matching-file-entries)),
which resolves (RFC 3986) like the listed one; a listed path with a `..`
segment isn't used. For a path with a
leading `/` (some TRS servers list paths so), a request builder SHOULD use
the bare form below: servers differ in how they serve such paths in a URL,
and the path without its `/` is not one that TRS listed.

The form with the path needs a TRS that accepts unencoded `/` in
`{relative_path}`, which TRS 2 allows ("unencoded paths ... are also
allowed") but older servers may not; a workflow whose primary descriptor
is at the top level (a path without `/`) works with every server.

Engines resolve the imports of a multi-file workflow (e.g., a WDL
`import "tasks/align.wdl"` or a CWL `run: tools/bwa-mem.cwl`) against the
URL of the importing document, as RFC 3986 says. Against the URL with the
path `main.wdl`, `tasks/align.wdl` resolves to
`.../PLAIN_WDL/descriptor/tasks/align.wdl`, a file of the tool version that
TRS serves (`{relative_path}` takes the paths that `/files` lists). Against
the bare `.../PLAIN_{descriptor_type}/descriptor`, which has no file name,
it resolves to `.../PLAIN_WDL/tasks/align.wdl`, which TRS doesn't serve.
The bare form MAY be used for single-file workflows, where nothing is
resolved against it.

Imports that resolve outside `.../descriptor/` (e.g., `../other.wdl` from a
primary descriptor at the top level) can't be served by TRS; such a workflow
needs `workflow_attachment` or a deployment that gets the workflow in
another way. Whether a WES fetches the `workflow_url` and its imports at all
depends on the deployment and the engine (see [WES](../adoption/wes.md)).
The test vectors in `tests/vectors/workflow-urls/` cover the URL and the
resolution of imports.

The schema itself is not part of the request: the server gets it from a
trusted source (see [Sources of schemas](../security.md#sources-of-schemas)).
How clients find the schema and the TRS fields is described in
[TRS](../adoption/trs.md#discovery-by-clients).

## From `workflow_params` back to input values

A WES server that validates requests (see [WES](../adoption/wes.md))
reverses the binding of the request's `workflow_type` before it validates
the values against `inputs`:

1. For each member of `workflow_params`, it finds the input that binds to
   the member's key (rule 2 above). An input can bind to several keys: the
   key of each `x-ga4gh-parameter` in its schema and the subschemas that
   apply to it in place (e.g., in the branches of `anyOf`), and its own
   name. Its *first* binding is the one that rule 2 uses when the schema
   doesn't depend on the value: the `x-ga4gh-parameter` nearest to the
   property's schema (of equally near ones, the first in the document), or
   else the name of the property. If several inputs can bind to the key,
   the member matches the input whose first binding it is; if that doesn't
   decide (none or several), the server MUST reject the request. If
   several members match the same input (e.g., under its
   `x-ga4gh-parameter` key and under its own name), the server MUST reject
   the request: only one of them would be validated, and the engine would
   get both. For `NFL`, keys are compared by their Nextflow names (see
   [Nextflow](#nextflow-nfl)): a member matches an input if its Nextflow
   name is that of one of the input's keys (e.g., `input-` matches the
   input `input`), and if two members have the same Nextflow name (e.g.,
   `input` and `input-`, or `outDir` and `out-dir`), whether they match
   inputs or not, the server MUST reject the request, as Nextflow would
   set the parameter only from the last of them. For `WDL`,
   a key without the prefix `<entry_point>.` matches no input. After the
   values are validated, the input MUST bind to the member's key for its
   value (rule 2 above); otherwise, the server MUST reject the request.
2. A member that matches no input stays under its own name, so that the
   schema (e.g., its `additionalProperties`) decides whether it is allowed;
   but if its name is the name of an input, which binds to another key
   (e.g., a `WDL` key without the prefix, or the name of an input renamed
   with `x-ga4gh-parameter`), the server MUST reject the request: under its
   own name, the member would be validated as that input, which the engine
   doesn't receive under this key.
3. For `CWL`, a `File` or `Directory` object at the location of a file
   reference becomes its `location`; an object without `location` is
   invalid (it MAY take `path` instead, where the deployment accepts paths).
   The server MUST reject objects with any other field, e.g., `contents`,
   which carries the data of a file in the request, `secondaryFiles` or
   `listing`, which carry more files past the checks of file references, or
   `basename`, which names the staged file; it MUST reject objects whose
   `class` doesn't match the `kind` of the file reference (`File` for
   `file`, `Directory` for `directory`), and objects at locations where no
   file reference applies. As for translators (rule 4 of "From input
   values to `workflow_params`"), it MUST reject keys that start with `$` or
   contain `:` anywhere in `workflow_params`, the directives and namespaced
   fields of the CWL loader.
4. Errors name the location in `workflow_params`, not in the input values:
   the first segment of the JSON Pointer is the key of the member in
   `workflow_params` (e.g., `/variant_calling.input_bam`), and the pointer of
   a CWL file value ends with `/location`.

The server MUST check every file value, also those it finds this way, by the
rules for servers in [URIs and file
references](../security.md#uris-and-file-references).

## Test vectors

Language-neutral test vectors in
[`tests/vectors/`](https://github.com/elixir-cloud-aai/ga4gh-io-schema/tree/main/tests/vectors)
of the repository test request builders against these rules, so that
implementations in other languages (e.g., TypeScript) can run the same cases:

```text
tests/vectors/
├── file-values/cases.json           # values of file references
├── wes-params/<descriptor type>/<case>/
│   ├── schema.json                  # an IO schema
│   ├── values.json                  # input values
│   ├── workflow_params.json         # the expected workflow_params, or
│   ├── error.json                   # {"pointer": …}: the values are rejected
│   └── options.json                 # optional: allowedSchemes, allowAbsolutePaths
└── wes-requests/<descriptor type>/<case>/
    ├── schema.json                  # an IO schema
    ├── workflow_params.json         # workflow_params of a request
    ├── values.json                  # the expected input values, or
    ├── error.json                   # {"pointer": …}: the request is rejected
    └── options.json                 # optional: also allowPaths
```

- **`wes-params`:** a request builder MUST produce `workflow_params.json`
  from `schema.json` and `values.json` (compared as JSON, not as text), or
  reject the values of a case with `error.json`; if it reports a location,
  it is the JSON Pointer `pointer` into the input values.
- **`wes-requests`:** a WES server MUST translate `workflow_params.json`
  back into `values.json` with the binding of the schema, or reject the
  request of a case with `error.json`; if it reports a location, it is the
  JSON Pointer `pointer` into `workflow_params`. Each valid case of
  `wes-params` is also a case of this direction: its `workflow_params.json`
  translates back into its `values.json`.
- **`file-values`:** each case has an `annotation` (`x-ga4gh-file`), a
  `value` and whether it is `valid`; a request builder MUST accept the
  valid values and reject the others.
- `options.json` and the cases of `file-values` can set the deployment's
  allow-list (`allowedSchemes`, default `["drs", "https"]`) and whether
  absolute paths are allowed (`allowAbsolutePaths`, default `false`); for
  `wes-requests`, also whether CWL `File` and `Directory` objects may give
  `path` instead of `location` (`allowPaths`, default `false`).

Error messages are not part of the vectors. The package runs them with
`tests/test_wes.py` against the Python API ([request
builders](../tools/wes-params.md#python-api), [WES
servers](../tools/wes-validate.md#python-api)).
