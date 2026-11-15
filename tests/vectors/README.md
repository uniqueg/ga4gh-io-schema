# Test vectors

Language-neutral test vectors of the GA4GH IO Schema Profile for request
builders and WES servers, for any implementation. They are part of the
conformance suite.

- `file-values/cases.json`: values of file references. Each case has a
  `name`, the `annotation` (`x-ga4gh-file`), the `value` and whether it is
  `valid`; optional `allowedSchemes` (the deployment's allow-list, default
  `["drs", "https"]`) and `allowAbsolutePaths` (default `false`).
- `wes-params/<descriptor type>/<case>/`: translation of input values into
  WES `workflow_params`. Each case has `schema.json` (an IO schema),
  `values.json` (the input values) and either `workflow_params.json` (the
  expected result) or `error.json` (the values must be rejected; `pointer`
  is the JSON Pointer of the offending value in the input values). An
  optional `options.json` has `allowedSchemes` and `allowAbsolutePaths`,
  with the defaults above.
- `wes-requests/<descriptor type>/<case>/`: translation of the
  `workflow_params` of a WES run request back into input values, by a WES
  server. Each case has `schema.json` (an IO schema), `workflow_params.json`
  and either `values.json` (the expected input values) or `error.json` (the
  request must be rejected; `pointer` is the JSON Pointer of the offending
  value in `workflow_params`, e.g., `/variant_calling.input_bam`, or
  `/reads/location` for a CWL file value). An optional `options.json` has
  `allowedSchemes`, `allowAbsolutePaths` and `allowPaths` (whether CWL
  `File` and `Directory` objects may give `path` instead of `location`,
  default `false`). The valid cases of `wes-params/` also translate back:
  their `workflow_params.json` gives their `values.json`.

Compare JSON documents, not their text. Error messages are not part of the
vectors. The rules are described in the
[Engine bindings](https://ga4gh-io-schema.readthedocs.io/en/latest/specification/engine-bindings/)
and [File references](https://ga4gh-io-schema.readthedocs.io/en/latest/specification/files/#values)
pages of the documentation.
