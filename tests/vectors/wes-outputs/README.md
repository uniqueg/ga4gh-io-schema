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

No case holds data of real users. The real runs below ran tiny test
workflows (no real data) on local Docker containers of the servers, in
November 2026 ([#55](https://github.com/uniqueg/ga4gh-io-schema/issues/55)).
Their run logs are `GET /runs/{run_id}` as the server returned it, cut down
to `run_id`, `state` and `outputs`, with host paths, run IDs and signatures
of presigned URLs replaced. The workflows are in
[`tests/data/wes-runs/`](../../data/wes-runs/).

| Case | Source |
| ----- | ----- |
| `cwltool-file-objects` | Real run: the output object of cwltool 3.3 (`--no-container`) for a test tool, paths anonymised |
| `sapporo-listing` | Real run: sapporo-service 2.4.2 with Nextflow 26.10.0, `main.nf`; the run log is the same as the one derived before from the source of sapporo-service (`sapporo/run.py`, `sapporo/schemas.py`) |
| `sapporo-cwltool-listing` | Real run: sapporo-service 2.4.2 with cwltool 3.3.20260925135507, `qc.cwl` |
| `weskit-listing` | Real run: WESkit (image `api:latest` of 2026-07, Snakemake 9.16.3), `variant-calling/Snakefile` with the parameters `{"title": "calls"}`, and S3 settings so that it adds presigned URLs (it signs them locally; no S3 store ran) |
| `toil-cwl-local-files` | Real run: Toil 9.5.0 `toil server` (`--bypass_celery`) with toil-cwl-runner and a local job store, `qc.cwl` |
| `cromwell-wdl-local-paths` | Real run: the WES API of Cromwell 92 in server mode, local backend, `rnaseq.wdl` |
| `cwl-remote-objects` | Derived: the CWL output object as cwltool writes it, with remote locations as Toil reports them when it writes to object storage (`--dest_bucket_base`; not captured: it needs an S3 store) |
| `wdl-qualified-names` | Derived: WDL outputs keyed by qualified names, as documented for Cromwell, miniwdl and Conquest, with `gs:` URIs of Cromwell on Google Cloud (not captured: it needs a cloud backend) |
| `wdl-local-paths` | Derived: miniwdl's outputs as absolute local paths (not captured: no WES server here runs miniwdl, and the WES server of Toil 9.5 fails WDL runs with a local job store, as it passes the CWL option `--outdir` to toil-wdl-runner); `cromwell-wdl-local-paths` has the same shape from a real run |
| `nextflow-no-outputs` | Derived: Nextflow on servers that report no outputs |
| other cases | Synthetic: rules of the specification (checks of listings, globs, partial and non-conformant runs, errors) |

The real runs differ from the derived cases in these points, which the
normaliser already handles:

- Sapporo lists the files of the output directory for every engine, also
  for CWL: `RunLog.outputs` isn't the CWL output object, and cwltool puts
  files directly into the output directory (files keep only their base
  name, `Directory` outputs their own name).
- WESkit lists the files that the run wrote into its working directory
  (`config.yaml`, results, `.snakemake/log/` and `.snakemake/metadata/`),
  in the order of the file system, but not the Snakefile, which it runs
  from its workflows directory. `S3` has a presigned URL (AWS signature
  version 2: `AWSAccessKeyId`, `Signature`, `Expires`) for every listed
  file, in a bucket named by the first four characters of the run ID.
- Toil's CWL `location`s are percent-encoded `file:` URIs (e.g.,
  `report%20%231.html`), its `path`s are not.
- The WES API of Cromwell reports absolute local paths on the local
  backend, under `cromwell-executions/<workflow>/<run_id>/`.
