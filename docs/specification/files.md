# File references

A file reference is a string parameter whose value refers to a file or a
directory. Its schema has `"type": "string"` and the annotation
`x-ga4gh-file`, which says what the string refers to:

```json
{
  "type": "string",
  "title": "Aligned reads",
  "x-ga4gh-file": {
    "kind": "file",
    "ontology": "http://edamontology.org/format_2572",
    "secondaryFiles": ["^.bai"],
    "schemes": ["drs", "https"]
  }
}
```

The annotation is allowed in every schema of an IO schema, at any depth: in
`inputs` and `outputs`, in the `items` of arrays (a list of files), and in the
columns of an `x-ga4gh-tabular-schema` (a sample sheet with file paths).

## The annotation

| Key | Value | Required | Meaning |
| ----- | ----- | ----- | ----- |
| `kind` | `file` or `directory` | yes | Whether the string refers to a file or to a directory. |
| `mediaType` | media type ([RFC 6838](https://www.rfc-editor.org/rfc/rfc6838)) without parameters, e.g., `text/csv` | no | Media type of the referenced file. Files only. |
| `ontology` | URI | no | Ontology term of the format of the referenced file or directory, e.g., an [EDAM](https://edamontology.org/) format term. |
| `compression` | `gzip`, `bgzip`, `bzip2`, `xz` or `zstd` | no | Compression of the referenced file. `bgzip` is block-compressed gzip: gzip tools read it, and index tools such as tabix need it. Files only. |
| `secondaryFiles` | non-empty list of suffix patterns | no | Files that must exist next to the referenced file (see [Secondary files](#secondary-files)). Files only. |
| `schemes` | non-empty list of URI schemes, in lowercase | no | URI schemes that values may use (see [Values](#values)). |

Other keys are rejected. The schema that carries the annotation:

- MUST have `"type": "string"`;
- MUST NOT have `format`: the profile defines the syntax of the values (see
  [Values](#values)), and `format: uri` would reject compact DRS identifiers
  (`drs://prefix:accession`) once formats are checked, and check nothing when
  they aren't;
- MUST NOT have `contentMediaType`: in JSON Schema, it describes the content of
  the string itself, not of the file that the string refers to; the media type
  of the file goes into `mediaType`.

It can have other keywords of the string, e.g., `pattern` to constrain file
names, `default`, `title` and `description`. `x-ga4gh-ontology` keeps its
meaning on a file reference: a term for the *data* of the parameter (e.g., an
EDAM data term), while `ontology` of the annotation names the *format* of the
file.

The meta-schema checks all of this (see [Meta-schema](meta-schema.md)), and
rejects schemes that run code in a browser or refer to local files
(`javascript`, `vbscript`, `data`, `blob`, `file`).

A file reference is optional if its name isn't listed in `required`, as for any
other parameter. A list of files is an array of file references:

```json
{
  "type": "array",
  "minItems": 1,
  "items": { "type": "string", "x-ga4gh-file": { "kind": "file", "compression": "gzip" } }
}
```

## Values

A value of a file reference is one of:

- **An absolute URI**: a scheme, a colon and the rest, e.g.,
  `https://data.example.org/reads_1.fastq.gz`, `s3://bucket/reads_1.fastq.gz`,
  `gs://bucket/reads_1.fastq.gz`, or a DRS URI: `drs://drs.example.org/314159`
  (host name) or `drs://dg.4503:6ca5c2a8` (compact identifier). A value has a
  scheme if it starts with a letter followed by letters, digits, `+`, `-` or
  `.` and a colon (`^[A-Za-z][A-Za-z0-9+.-]*:`). Schemes are compared in
  lowercase. Apart from the scheme, the profile doesn't check the syntax of
  the URI: compact DRS identifiers aren't valid URIs under
  [RFC 3986](https://www.rfc-editor.org/rfc/rfc3986), because the part after the
  colon isn't a port number.
- **A path**: a value without a scheme, in inputs only. A relative path refers
  to a file attached to the run request (`workflow_attachment` of WES); a path
  whose first segment contains a colon starts with `./`, so that it doesn't
  look like a scheme. Absolute paths refer to the file system of the execution
  side and are accepted only by deployments with a shared file system, in
  directories that they allow. [URIs and file
  references](../security.md#uris-and-file-references) has the rules that
  servers apply to paths (e.g., no `..` segments).

If the annotation has `schemes`, values MUST be absolute URIs with one of them;
paths are not allowed. Without `schemes`, values use the schemes of the
deployment's allow-list, or are paths. A value passes only if its scheme is on
both lists: `schemes` narrows the allow-list of the deployment and never
extends it. A directory URI may end with `/`.

Clients SHOULD check values against these rules before they submit a run, and
servers that validate requests MUST check them (see [Security
considerations](../security.md#uris-and-file-references)). JSON Schema
validators don't, because the rules are not expressed in JSON Schema keywords;
they check only that the value is a string and the other keywords of the
schema (e.g., `pattern`).

## Secondary files

Secondary files are files that a tool needs next to the referenced file,
typically indexes (a BAM file needs its `.bai`; BWA needs five index files next
to the reference). They follow the suffix patterns of
[CWL](https://www.commonwl.org/v1.2/CommandLineTool.html#SecondaryFileSchema):
the suffix is appended to the name of the referenced file, after each leading
`^` has removed one extension.

| Referenced file | Pattern | Secondary file |
| ----- | ----- | ----- |
| `sample.bam` | `.bai` | `sample.bam.bai` |
| `sample.bam` | `^.bai` | `sample.bai` |
| `calls.vcf.gz` | `.tbi` | `calls.vcf.gz.tbi` |
| `calls.vcf.gz` | `^^.idx` | `calls.idx` |

A pattern is a suffix of letters, digits, `_`, `.`, `+` and `-`, optionally
after carets; it can't contain `/`, so it can't point outside the directory of
the referenced file. Every listed secondary file is required. Clients don't
send secondary files as values: the execution side finds them next to the
referenced file when it stages it, and fails the run, or rejects the request,
if one is missing.

For URIs whose last path segment is the file name (e.g., `https`, `s3`, `gs`),
the pattern is applied to that segment. DRS identifiers don't contain the
file name; how the execution side finds the secondary files of a DRS object
(e.g., in the same DRS bundle, or by the object's `name`) is not defined by
version 0.3 of the profile.

## Mapping to workflow languages

Converters (see [Converters](../tools/converters.md)) emit file references for
the file types of workflow languages:

| Workflow language | Source | IO schema |
| ----- | ----- | ----- |
| CWL | `File` | `{"type": "string", "x-ga4gh-file": {"kind": "file"}}` |
| CWL | `Directory` | `{"type": "string", "x-ga4gh-file": {"kind": "directory"}}` |
| CWL | `format` (an ontology term) | `ontology` |
| CWL | `secondaryFiles` with patterns and `required: true` (the default for inputs) | `secondaryFiles` with the patterns |
| CWL | optional secondary files (`required: false`, or a pattern ending with `?`), expressions (`$(...)`, `${...}`) | No equivalent; the converter reports them |
| CWL | `File?`, `File[]` | not in `required`; an array of file references |
| WDL | `File` | `{"type": "string", "x-ga4gh-file": {"kind": "file"}}` |
| WDL | `Directory` (WDL 1.2) | `{"type": "string", "x-ga4gh-file": {"kind": "directory"}}` |
| WDL | `File?`, `Array[File]` | not in `required`; an array of file references |
| WDL | index files, declared as separate inputs | separate file references; WDL has no secondary files |
| nf-schema | `"format": "file-path"` | `"x-ga4gh-file": {"kind": "file"}`, without `format` |
| nf-schema | `"format": "directory-path"` | `"x-ga4gh-file": {"kind": "directory"}`, without `format` |
| nf-schema | `"format": "path"` (file or directory) | `"x-ga4gh-file": {"kind": "file"}`, unless the pipeline documents a directory; the converter reports the choice |
| nf-schema | `"format": "file-path-pattern"` (a glob) | No equivalent: a glob is not a reference; the converter keeps a plain string and reports it |
| nf-schema | `mimetype` | `mediaType` |
| nf-schema | `schema` (sample sheet) | `x-ga4gh-tabular-schema` (see [Keywords](keywords.md#tabular-data-and-cloud-sovereignty)) |
| nf-schema | `pattern` | `pattern`, unchanged (it constrains the value) |
| nf-schema | `exists` | dropped: Nextflow checks it on the execution side, and skips it for object-store paths |

The *values* of file references become the file objects or paths of each
engine (e.g., CWL `{"class": "File", "location": …}`) when a client builds the
`workflow_params` of a WES request; that translation is defined separately.

## Clients

Clients can use the annotation to render inputs and outputs:

- `kind`: a file picker or a directory picker (the `file-picker` and
  `directory-picker` widgets of the vocabulary are the defaults);
- `mediaType`, `ontology` and `compression`: filter what a picker offers, and
  choose a viewer for outputs (see [Rendering schemas and
  outputs](../security.md#rendering-schemas-and-outputs));
- `schemes`: which sources to offer, e.g., a DRS browser for `drs` (see
  [Portals and clients](../adoption/portals.md)).
