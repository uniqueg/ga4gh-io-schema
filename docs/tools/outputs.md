# Output normaliser

The output normaliser builds the [normalised outputs
object](../specification/outputs.md#the-normalised-outputs-object) of a WES
run: it takes what the WES server reports for the run (`RunLog.outputs`),
keys it by the outputs of an IO schema, validates it, and reports what
doesn't fit. It implements the rules of [Finding
outputs](../specification/outputs.md#finding-outputs) and the requirements
of the class [Output normaliser](../specification/conformance.md#output-normaliser),
except those for showing outputs (requirements 2 and 5), which are the
client's.

The normaliser never fetches anything: not the files of the run, not the
URIs of outputs, and not references of the schema. It works on the run log,
the files that the server lists, and the options that the deployment gives.

## Command-line interface

```bash
ga4gh-io-schema outputs --schema my-workflow.schema.json --run-log run-log.json \
    --output-dir https://wes.example.org/runs/7/outputs
```

`--run-log` is the WES `RunLog` of the run (`GET /runs/{run_id}`). The
options:

| Option | Needed for | Meaning |
| --- | --- | --- |
| `--output-dir URI` | servers that list files; engines that report paths | The URI of the output directory of the run: the URI prefix under which the server keeps its files (see [`x-ga4gh-output-glob`](../specification/outputs.md#x-ga4gh-output-glob)). A trailing `/` is removed. |
| `--local-dir PATH` | engines that report local paths | The absolute path of the output directory as the engine sees it. Absolute paths and `file:` URIs that the engine reports under it become URIs under `--output-dir`. |
| `--files PATH` | servers that list files elsewhere | A JSON array of the files of the run, as paths relative to the output directory or as URIs under it. It replaces the listing of the run log, if any. |

The command writes a report (indented JSON; one line with `--json`):

```json
{
  "state": "COMPLETE",
  "conformance": "conformant",
  "outputs": {
    "qc_report": "https://wes.example.org/runs/7/outputs/multiqc/multiqc_report.html",
    "alignments": [
      "https://wes.example.org/runs/7/outputs/alignments/s1.bam",
      "https://wes.example.org/runs/7/outputs/alignments/s2.bam"
    ]
  },
  "errors": [],
  "removed": {},
  "ambiguous": {},
  "unconverted": [],
  "undeclared": {},
  "unmatchedFiles": ["https://wes.example.org/runs/7/outputs/counts/s1.tsv"],
  "skippedFiles": []
}
```

| Key | Meaning |
| --- | --- |
| `state` | The WES state of the run. Only runs in a final state (`COMPLETE`, `EXECUTOR_ERROR`, `SYSTEM_ERROR`, `CANCELED`, `PREEMPTED`) are normalised; others are an error. |
| `conformance` | `conformant` or `non-conformant` for a run that completed: whether `outputs` is valid against the schema's `outputs`. `partial` for a run that ended in another state. Clients show non-conformant and partial outputs with a warning (see [Runs that don't complete](../specification/outputs.md#runs-that-dont-complete)). |
| `outputs` | The normalised outputs object. |
| `errors` | Validation errors, each with the `output`, the `location` (a JSON path in `outputs`) and a `message`. For a completed run, the outputs are kept as they are; for a partial run, the outputs with errors are left out. |
| `removed` | The outputs of a partial run that were left out because their values are invalid. |
| `ambiguous` | Outputs of one file whose glob matches several files, with the URIs of the matches. The outputs are absent. |
| `unconverted` | Outputs reported by name whose values can't be given as URIs (e.g., a local path outside `--local-dir`, or a relative path without `--output-dir`), with the reason. The outputs are absent. |
| `undeclared` | Outputs that the engine reports by name but the schema doesn't declare, by their names in the engine. Clients MAY offer them for download, as files without a description. |
| `unmatchedFiles` | URIs of listed files that no output found. |
| `skippedFiles` | Entries of the listing that failed the checks of [`x-ga4gh-output-glob`](../specification/outputs.md#x-ga4gh-output-glob) (e.g., a `..` segment), with the reason. |

The exit status is 0 whenever the outputs could be normalised, also for
non-conformant and partial runs: check `conformance`. It is 1 if the schema
doesn't conform to the profile, the run hasn't ended, `RunLog.outputs` has
no supported shape, the options are inconsistent, or the schema has a
reference that can't be resolved; 3 if a file can't be read (see [Exit
status](cli.md#exit-status)).

## Supported shapes

The shape of `RunLog.outputs` is detected:

| Shape | Reported by | How outputs are found |
| --- | --- | --- |
| An object keyed by output name | cwltool and Toil (the CWL output object); Cromwell, miniwdl and Conquest for WDL (names qualified with the workflow name, e.g., `rnaseq.qc_report`) | By name. The name of an output is `name` of its `x-ga4gh-parameter` or its property name, qualified with `entry_point` of `x-ga4gh-workflow` for WDL. CWL `File` and `Directory` objects give their `location` (or `path`); `null` values, also items of arrays and fields of objects, are absent. |
| An array of files | Sapporo: objects with `file_name`, relative to the output directory (`{base_url}/runs/{run_id}/outputs`), and `file_url`; or strings, paths or URIs | By glob, from the listing; `file_url` isn't used. |
| An object with only `filesystem` (and `S3`) | WESkit: `filesystem` lists the files of the working directory of the run, relative to it; `S3` the same files as presigned URLs | By glob, from `filesystem`. The presigned URLs of `S3` carry credentials and are ignored; they never reach the report. If the schema declares an output named `filesystem` or `S3`, the object is taken as outputs by name. |
| Absent, `null` or `{}` | Nextflow and Snakemake on most WES servers | By glob, if `--files` lists the files of the run; otherwise nothing is found. |

Rules for values found by name:

- A value whose schema is a file reference is turned into a URI: URIs other
  than `file:` are kept as they are; absolute paths and `file:` URIs (of no
  host or `localhost`) under `--local-dir`, and relative paths, become URIs
  under `--output-dir`, built as for listed files (each segment
  percent-encoded); others are reported as `unconverted`.
- Arrays, objects with `properties` (records) and objects with a file
  reference as `additionalProperties` (files keyed by name) are converted
  item by item, following local `$ref`s. Other values (also tuples with
  `prefixItems`) are kept as they are, for validation to report.
- Values that don't fit their schema (e.g., a single file for a list) are
  kept as they are: the normaliser never changes outputs to make them valid.

Rules for the listing are those of
[`x-ga4gh-output-glob`](../specification/outputs.md#x-ga4gh-output-glob):
entries are checked before globs are matched, secondary files of a match
are not values of their own, several matches of an array are sorted by path,
and directories are those that contain listed files.

## Limits

- **Nextflow and Snakemake:** current WES servers don't report their outputs
  by name and, except WESkit and Sapporo, don't list the files of a run.
  Their outputs are found only by glob, from a listing that the server (or
  `--files`) provides; scalars can't be found that way.
- **Output directory:** the normaliser can't tell the output directory of a
  run from the run log; the deployment gives it (`--output-dir`). Without
  it, a run that lists files is an error.
- **WDL without `x-ga4gh-workflow`:** names are qualified with the entry
  point only if the schema has `x-ga4gh-workflow` with `descriptor_type`
  `WDL`; otherwise the names of properties are used as they are.
- **Allow-list of schemes:** the normaliser checks file references against
  `schemes` of their annotation (as part of validation), not against the
  allow-list of the deployment. Clients check every output URI against their
  allow-list before they show it (requirement 2 of [Output
  normaliser](../specification/conformance.md#output-normaliser)).

## Test vectors

Language-neutral test vectors for output normalisers are in
[`tests/vectors/wes-outputs/`](https://github.com/uniqueg/ga4gh-io-schema/tree/main/tests/vectors/wes-outputs),
one directory per case, described in its `README.md`. They cover the shapes
above, the checks of listings, glob matching, and completed, non-conformant
and partial runs. The case `cwltool-file-objects` is the output of a real
cwltool run, with its paths anonymised; the others are written from the
shapes in the documentation and source code of the engines and servers.
`tests/test_outputs.py` runs them against this package.

## Python API

::: ga4gh_io_schema.outputs.normalise_outputs

::: ga4gh_io_schema.outputs.NormalisedOutputs

::: ga4gh_io_schema.outputs.NormalisationError
