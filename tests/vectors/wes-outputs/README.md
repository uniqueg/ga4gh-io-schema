# Test vectors: outputs of WES runs

Language-neutral test vectors for output normalisers: software that builds
the normalised outputs object of a WES run (see the Outputs page of the
specification and the Output normaliser page of the tools). They are part of
the conformance suite.

Each directory is one case:

- `schema.json`: the IO schema.
- `run_log.json`: the WES `RunLog` of the run (`state` and `outputs`; other
  fields are left out).
- `options.json` (optional): what the deployment gives the normaliser:
  `outputDir` (the URI of the output directory of the run), `localDir` (the
  local path of the output directory, as the engine reports it) and `files`
  (a listing of the files of the run that replaces the one of the run log).
- Either `expected.json`, the expected result, or `error.json`: the input
  must be rejected as a whole (e.g., the run hasn't ended).

`expected.json` has a `description` and:

- `conformance`: `conformant`, `non-conformant` or `partial`;
- `outputs`: the normalised outputs object;
- optionally, what the normaliser reports, each empty (`[]` or `{}`) if
  absent:
  - `removed`: array of the names of outputs of a partial run left out as
    invalid, sorted;
  - `ambiguous`: object with the names of one-file outputs with several
    matches as keys, and the URIs of the matches, sorted by path, as
    values;
  - `unconverted`: array of the names of outputs reported by name whose
    values can't be given as URIs, sorted;
  - `undeclared`: array of the names in the engine of outputs that the
    schema doesn't declare, sorted;
  - `unmatchedFiles`: array of the URIs of listed files that no output
    found, sorted by code point;
  - `skippedFiles`: array of the listed entries that failed the checks, in
    the order of the listing, as they are reported: URIs without user
    information, query and fragment, objects and arrays as
    `{"type": "object"}` or `{"type": "array"}`, other values as
    listed.

Compare JSON values, not their text. In `removed`, `unconverted` and
`undeclared`, only the names of reported outputs are compared, not their
values (`ambiguous` compares the URIs too); a normaliser's own report may carry more
(e.g., the values and reasons). Validation errors, their messages and the
reasons of reports are not part of the vectors.

## Provenance

No case holds data of real users or runs other than the one below.

| Case | Source |
| ----- | ----- |
| `cwltool-file-objects` | Real run: the output object of cwltool 3.3 (`--no-container`) for a test tool, paths anonymised |
| `cwl-remote-objects` | Derived: the CWL output object as cwltool writes it, with remote locations as Toil reports them when it writes to object storage |
| `wdl-qualified-names` | Derived: WDL outputs keyed by qualified names, as documented for Cromwell, miniwdl and Conquest |
| `wdl-local-paths` | Derived: miniwdl's outputs as absolute local paths |
| `sapporo-listing` | Derived from the source of sapporo-service: `sapporo/run.py` (the listing of `outputs`, `file_url` as `{base_url}/runs/{run_id}/outputs/{file_name}`) and `sapporo/schemas.py` (`FileObject`) |
| `weskit-listing` | Derived from the source of WESkit: `weskit/tasks/submission_worker.py` (paths relative to the working directory), `weskit/tasks/monitoring_worker.py` (`outputs["filesystem"]`) and `weskit/classes/Manager.py` (`outputs["S3"]`, presigned URLs) |
| `nextflow-no-outputs` | Derived: Nextflow on servers that report no outputs |
| other cases | Synthetic: rules of the specification (checks of listings, globs, partial and non-conformant runs, errors) |
