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
- optionally, what the normaliser reports, each empty if absent:
  `removed` (names of outputs of a partial run left out as invalid),
  `ambiguous` (names of one-file outputs with several matches, with the
  URIs of the matches), `unconverted` (names of outputs reported by name
  whose values can't be given as URIs), `undeclared` (names in the engine of
  outputs that the schema doesn't declare), `unmatchedFiles` (URIs of listed
  files that no output found, sorted by code point) and `skippedFiles` (the
  listed entries that failed the checks, in the order of the listing).

Compare JSON values, not their text; names in `removed`, `unconverted` and
`undeclared` are sorted. Validation errors, their messages and the reasons
of reports are not part of the vectors.

The case `cwltool-file-objects` is the output object of a real cwltool run,
with its paths anonymised. The others are written from the shapes that the
documentation and source code of the engines and servers describe (Toil,
Cromwell, miniwdl, Conquest, Sapporo and WESkit); they hold no data of real
runs.
