# Outputs

The `outputs` of an IO schema describe what a run of the workflow returns.
Clients use them to show the results of a run (in a viewer, or for
download), and agents to read them. This page defines the outputs schema,
the shapes of output values, the *normalised outputs object* that clients
consume, how the outputs of a run are found in what a WES server returns,
and what changes when a run fails.

The key words "MUST", "MUST NOT", "SHOULD", "SHOULD NOT" and "MAY" are to
be interpreted as described in [BCP 14](https://www.rfc-editor.org/info/bcp14)
([RFC 2119](https://www.rfc-editor.org/rfc/rfc2119),
[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)) when, and only when,
they appear in all capitals.

## The outputs schema

`outputs` is optional:

- **Without `outputs`**, the IO schema describes no outputs. Clients offer
  whatever the server reports for a run for download only, as files without
  a description.
- **With `outputs`**, it is an object schema whose `properties` are the
  outputs, each named by its property. The meta-schema rejects a boolean
  schema, a `type` other than `object`, and references and applicators
  (`$ref`, `allOf`, `if` and the like) on `outputs` itself: the outputs are
  its direct `properties`, so that normalisers find them without resolving
  anything. `"properties": {}` says that the workflow has no named outputs.

Schemas SHOULD have `outputs` where the workflow language declares outputs,
and converters MUST convert the outputs that it declares. Outputs listed in
`required` are produced by every run that completes; the others are
optional. The normalised outputs object never has keys other than those of
`properties` (see below); `"additionalProperties": false` says so in the
schema, and lets validators catch a normaliser that adds others.

The [examples](examples.md) show the shapes below: the workflow example has
a report, a list of files, files keyed by sample and a number; the tool
example one file.

## Values

Each output has a value in the shape of its schema:

| Output | Schema | Value |
| ----- | ----- | ----- |
| A file or directory | a [file reference](files.md) | an absolute URI |
| A list of files (e.g., one per sample) | `"type": "array"` with a file reference as `items` | an array of absolute URIs |
| Files keyed by sample, or by another name known only at run time | `"type": "object"` with a file reference as `additionalProperties` | an object of absolute URIs |
| A record (e.g., a CWL record, a WDL struct) | `"type": "object"` with `properties` | an object |
| A scalar (e.g., a count, a version, a flag) | `string`, `number`, `integer` or `boolean` | the JSON value |

These shapes nest: file references are allowed at any depth (e.g., a list of
records, each with a file). Rules for values:

- **File references** are absolute URIs. Paths are allowed in inputs only
  (see [Values](files.md#values)); a normaliser turns paths that an engine
  reports into URIs of the storage where the server keeps the outputs, or
  leaves the output out and reports it.
- **Secondary files** are not part of the value. They lie next to the file,
  as its `secondaryFiles` patterns say (see [Secondary
  files](files.md#secondary-files)), and clients find them there.
- **Outputs that a run didn't produce** are absent, never `null`. Schemas
  SHOULD NOT allow `null` in outputs; normalisers leave out the `null`
  values that engines report for optional outputs (e.g., WDL `File?`), and
  the `null` items of lists (e.g., WDL `Array[File?]`).
- **Outputs known only at run time:** the number of files in a list, and
  the keys of files keyed by sample, are known only when the run has
  finished; the schema describes their shape, not their number. Outputs that
  an engine reports but the schema doesn't declare are not part of the
  normalised outputs object. Normalisers report them separately, and clients
  MAY offer them for download, as files without a description.

## The normalised outputs object

The normalised outputs object of a run is a JSON object:

- its keys are keys of `outputs.properties`, the names of the outputs;
- its values are the outputs of the run, in the shape of their schemas (see
  [Values](#values));
- it lacks the outputs that the run didn't produce.

It is what clients and viewers consume: the keywords of an output's schema
(`x-ga4gh-ui-widget`, `x-ga4gh-ontology`, `x-ga4gh-file` and the others)
apply to the value under its key. For a run that completed (WES state
`COMPLETE`), the object MUST be valid against `outputs`: the run *conforms*
to the schema. A normaliser validates the object. If it isn't valid (e.g., a
required output is missing, or a list has fewer files than `minItems`), the
normaliser reports the outputs of the run as non-conformant, with the
errors, and still returns the object; it never drops or changes outputs to
make the object valid. Clients show non-conformant outputs with the same
warning as the outputs of [runs that don't
complete](#runs-that-dont-complete), but all outputs are kept. For the
workflow
example ([Example 1](examples.md#example-1-full-workflow-with-a-sample-sheet)):

```json
{
  "qc_report": "s3://example-bucket/runs/7/multiqc/multiqc_report.html",
  "alignments": [
    "s3://example-bucket/runs/7/alignments/s1.bam",
    "s3://example-bucket/runs/7/alignments/s2.bam"
  ],
  "gene_counts": {
    "s1": "s3://example-bucket/runs/7/counts/s1.tsv",
    "s2": "s3://example-bucket/runs/7/counts/s2.tsv"
  },
  "samples_passed_qc": 2
}
```

A *normaliser* builds the object from what the WES server reports for a run
(`RunLog.outputs`, and the files of the run if the server lists them). It
can run in a client or in a gateway in front of WES servers. WES 1.1 has no
field for the object; how structured outputs could become part of WES is
discussed in [WES pull request #226](../related-work.md#wes-pull-request-226).
The `ga4gh-io-schema` package has a normaliser (see [Output
normaliser](../tools/outputs.md)).

## Finding outputs

Engines and WES servers report outputs in different shapes (see [Notes on
engines and servers](#notes-on-engines-and-servers)). A normaliser finds
each output of `outputs.properties` in this order:

1. **By name.** If the engine reports the output by name, its value is the
   reported value, in the shape of the schema (e.g., the `location` of a CWL
   `File` object). The name of an output in the engine is the name of its
   property, qualified as the workflow language requires (e.g., with the
   name of the WDL workflow), unless the engine binding of the output names
   another one (`name` of `x-ga4gh-parameter`, see [Parameter
   bindings](identity.md#parameter-bindings)). `x-ga4gh-output-glob` is then
   ignored, also if the reported value is `null` (the output is then
   absent).
2. **By glob.** Otherwise, if the output has `x-ga4gh-output-glob`, the
   normaliser matches the glob against the files of the run (see below).
3. Otherwise, the output is absent. That is normal for an optional output;
   for a required output of a completed run, validation reports it.

### `x-ga4gh-output-glob`

`x-ga4gh-output-glob` finds an output among the files of a run, for engines
and servers that don't report outputs by name:

```json
"alignments": {
  "type": "array",
  "items": {
    "type": "string",
    "x-ga4gh-file": { "kind": "file", "secondaryFiles": [".bai"] }
  },
  "x-ga4gh-output-glob": "alignments/*.bam"
}
```

The glob is relative to the **output directory of the run**: the directory,
or URI prefix, under which the server keeps the files of the run (e.g.,
Nextflow's output directory, Snakemake's working directory). It is matched
against the paths of the run's files relative to that directory, as the
server lists them.

The listing comes from the run, so a normaliser MUST check it before it
matches:

- It MUST skip listed paths that are absolute, have empty, `.` or `..`
  segments, contain backslashes or control characters, or whose first
  segment contains a colon, and report them.
- It builds the URI of a match by percent-encoding each segment of the path
  (so that `?`, `#` and `%` in names stay part of the name) and appending
  the segments to the URI of the output directory, not by resolving the path
  as a URI reference. Every character other than the unreserved characters
  of [RFC 3986](https://www.rfc-editor.org/rfc/rfc3986#section-2.3)
  (letters, digits, `-`, `.`, `_` and `~`) is percent-encoded, as UTF-8 with
  uppercase hexadecimal digits, so that every normaliser builds the same URI
  (e.g., `s 1#.tsv` becomes `s%201%23.tsv`).
- Where the server lists URIs instead of paths, a normaliser MUST accept a
  listed URI only if it starts with the URI of the output directory with
  exactly one trailing `/`, and has no query or fragment. It derives the
  relative path from the rest: split at `/`, each segment percent-decoded.
  The decoded path MUST pass the checks of listed paths above (e.g., a
  listed `…/out/../8/secret.bam` is skipped), and a decoded segment MUST
  NOT contain `/` (e.g., `…/out/x%2F..%2F..%2Fsecret.bam` is skipped:
  some storage treats `%2F` as `/`). The URI of a match is built from the
  decoded path as above.

Syntax:

- Segments are separated by `/`. In a segment, `*` matches any characters
  (also none) and `?` exactly one character, but neither matches `/`; a
  segment `**` matches any number of segments (also none). All other
  characters match themselves, case-sensitively; `*` and `?` also match a
  leading `.`.
- Not allowed (the meta-schema rejects them): absolute paths, empty segments
  (so also a trailing `/`), `.` and `..` segments, `**` within a segment
  (e.g., `**.bam`), a colon in the first segment (it would look like a URI
  scheme, and normalisers skip such listed paths), backslashes, control characters (C0, DEL and C1), line
  and paragraph separators, and brackets and braces (`[`, `]`, `{`, `}`),
  whose meaning differs between glob dialects.
- A glob always matches at least one segment: `**` alone matches every
  listed path, never the output directory itself.

What a glob finds depends on the schema of the output, counted after
secondary files have been removed from the matches (see below):

| Schema of the output | No match | One match | Several matches |
| ----- | ----- | ----- | ----- |
| File reference | absent | its URI | absent; the normaliser reports the ambiguity |
| Array of file references | absent | an array with its URI | an array of their URIs, sorted by path (by Unicode code points) |

- For `kind: file`, a glob matches the paths of files; for `kind:
  directory`, the paths of directories that contain listed files, directly
  or at any depth.
- A match that is a secondary file of another match (by the
  `secondaryFiles` patterns of the output) is not a value of its own: the
  glob `alignments/*` finds `s1.bam`, not `s1.bam.bai` next to it.
- The meta-schema allows the keyword only on a file reference and on an
  array whose `items` is a file reference written in place (not a `$ref`),
  without `prefixItems`, not on other types. It has a meaning only on the
  schema of a direct property of `outputs`; elsewhere (e.g., in a field of a
  record, or in `inputs`), clients ignore it. The meta-schema deliberately
  doesn't enforce this, as for the other keywords that it checks at any
  depth.
- A normaliser matches globs only against the files that the server lists
  for the run. It doesn't browse storage on its own. The syntax of the glob
  and the checks of the listing above keep matches inside the output
  directory, as far as the listing goes: files that a run links to from
  elsewhere (e.g., symbolic links) are the server's to exclude.
- A value found by glob can still be invalid against the schema of its
  output (e.g., fewer files than `minItems`, or a URI scheme outside
  `schemes`); the rules of [the normalised outputs
  object](#the-normalised-outputs-object) apply.

## Runs that don't complete

A run that ended in another state than `COMPLETE` (e.g., `EXECUTOR_ERROR`,
`SYSTEM_ERROR` or `CANCELED`) can have produced some of its outputs. Its
normalised outputs object has the outputs that were found. It is checked
property by property, not against the whole `outputs` schema: each value
MUST be valid against the schema of its property, and `required` doesn't
apply. A normaliser leaves out outputs whose values aren't, and reports
them. Clients MUST show such outputs as partial (e.g., "the run failed; these outputs were
produced"), and SHOULD warn that they may be incomplete (e.g., a truncated
file). Normalisers build the object only for runs in a final state.

## Notes on engines and servers

How the workflow languages declare outputs, how engines and WES servers
report them, and how a schema finds them. The behaviour of engines and
servers is informative: it was surveyed in November 2026 for
[#11](https://github.com/uniqueg/ga4gh-io-schema/issues/11), with the WES
servers Sapporo, WESkit and Conquest (a WES server that runs workflows from
Git repositories), and may change with new versions. The test vectors of
the normaliser record the shapes that it supports (see [Output
normaliser](../tools/outputs.md#supported-shapes)).

| Language | Declared outputs | Reported by | How a schema finds them |
| ----- | ----- | ----- | ----- |
| CWL | `outputs` of a `Workflow` or `CommandLineTool`, typed (`File`, `Directory`, arrays, records, optional types with `?`) | cwltool and Toil: the CWL output object, keyed by output id; files as `File` objects with `location` and `secondaryFiles` | By name; the value of a file is its `location`. `outputBinding.glob` is relative to a tool's working directory, not to the output directory of the run; converters don't copy it into `x-ga4gh-output-glob`. |
| WDL | the `output` section, typed (`File`, `Array[File]`, `Map[String, File]`, structs, optional types with `?`) | Cromwell, miniwdl and Conquest: keyed by the name qualified with the workflow name (e.g., `rnaseq.qc_report`); `null` for optional outputs that weren't produced | By name; `Map[String, File]` becomes files keyed by name. |
| Nextflow | typed workflow outputs (the `output` block, stable since Nextflow [25.10](https://docs.seqera.io/nextflow/migrations/25-10)), published under the output directory; `nextflow_schema.json` describes parameters only; the draft [pipeline spec](../related-work.md#nextflow-pipeline-spec-6900) adds outputs | Not by name, in the WES servers checked | By glob, relative to the output directory. A converter can take outputs from the pipeline spec once it is adopted. |
| Snakemake | no named outputs of the workflow; the `output` files of rules, relative to the working directory (usually the targets of the first rule, e.g., `rule all`) | Not by name, in the WES servers checked | By glob, relative to the working directory. |

WES servers that run several engines differ too: Sapporo reports a list of
files without names, and WESkit an object with a list of files
(`{"filesystem": [...]}`). Outputs of these servers are found by glob, from
these lists. Scalars (e.g., a count) can't be found by glob; for engines
without named outputs, schemas declare only outputs that are files.

## Security

Output values come from the run, which may have processed files supplied by
users. Clients MUST check the scheme of every output URI against their
allow-list before they show it as a link or load it into a viewer, and
follow the rules of [Rendering schemas and
outputs](../security.md#rendering-schemas-and-outputs). Normalisers check
the files that a server lists before they match globs against them (see
[`x-ga4gh-output-glob`](#x-ga4gh-output-glob)).

## Chaining workflows (deferred)

Because one workflow's output can be another workflow's input, the `x-ga4gh-ontology` terms on both sides of the contract hint which outputs may fit which inputs. Chaining workflows by these terms is deferred in version 0.3 (see [Roadmap](../roadmap.md#deferred)): a single exact term is not enough to decide that a file fits, as it doesn't cover more specific terms (subclasses), and it says nothing about, e.g., the genome build, the compression or the VCF version. The profile defines no matching rules; clients that suggest candidates do so on their own terms.

See also [the `x-ga4gh-*` vocabulary](keywords.md#the-x-ga4gh-vocabulary).
