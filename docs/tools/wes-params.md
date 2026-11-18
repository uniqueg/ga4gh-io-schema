# WES parameters

The `wes-params` subcommand of the [command-line interface](cli.md), and the
`ga4gh_io_schema.wes` module, turn input values into the `workflow_params`
of a GA4GH WES run request, or into a full `RunRequest`, by the rules of
[Engine bindings](../specification/engine-bindings.md). They implement the
conformance class [Request builder](../specification/conformance.md#request-builder)
for the translation; submitting the request is left to the caller. The
reverse, for WES servers, is [WES request validation](wes-validate.md).

## Command-line interface

```bash
ga4gh-io-schema wes-params --schema workflow.schema.json --values values.json
```

The command:

1. validates the schema against the GA4GH IO Profile;
2. takes the engine binding from the schema's `x-ga4gh-workflow`
   (descriptor type, its version and the entry point);
3. validates the values (a JSON object, an instance of the schema's
   `inputs`) against `inputs`, and every value of a file reference against
   the rules of [Values](../specification/files.md#values) and the
   deployment's allow-list of schemes; for CWL, it rejects `File` and
   `Directory` objects and keys that start with `$` or contain `:`
   (directives and namespaced fields of the CWL loader, e.g., `$include` or
   `cwltool:overrides`) in the values, see rule 4 of [From input
   values to `workflow_params`](../specification/engine-bindings.md#from-input-values-to-workflow_params);
   for Nextflow, it rejects values of two inputs whose keys Nextflow
   renames to the same parameter (e.g., `out-dir` and `outDir`, see
   [Nextflow](../specification/engine-bindings.md#nextflow-nfl));
4. writes the `workflow_params`, as indented JSON (with `--json`, on one
   line).

For the inputs of [Example 3](../specification/examples.md#example-3-workflow-bound-to-an-engine)
and these values:

```json
{
  "input_bam": "https://data.example.org/sample.bam",
  "sample_names": ["NA12878"],
  "caller_threads": 8
}
```

it writes:

```json
{
  "variant_calling.input_bam": "https://data.example.org/sample.bam",
  "variant_calling.sample_names": ["NA12878"],
  "variant_calling.call_variants.threads": 8
}
```

Options:

- `--descriptor-type`, `--type-version` and `--entry-point` fill in the
  fields of the binding that the schema lacks (e.g., the version of the
  workflow language from TRS, or all of them for a schema without
  `x-ga4gh-workflow`); a value that differs from the schema is an error.
- `--allow-scheme SCHEME` (repeatable) sets the deployment's allow-list of
  URI schemes for file references; the default is `drs` and `https`. Schemes
  that run code in a browser or refer to local data (`javascript`, `data`,
  `file` and the others that the meta-schema rejects in `schemes`) can't be
  allowed.
- `--allow-absolute-paths` accepts absolute paths as file references, for
  deployments with a shared file system. Relative paths, which refer to
  files attached to the request (`workflow_attachment`), are always
  accepted, without `..` segments.
- `--request` writes a `RunRequest` with `workflow_params`,
  `workflow_type`, `workflow_type_version` and `workflow_url`, which needs
  the version of the workflow language and either `--workflow-url URL` or
  `--trs-url URL`. With `--trs-url` (the base URL of a TRS API, e.g.,
  `https://trs.example.org/ga4gh/trs/v2`), the `workflow_url` is the plain
  primary descriptor of the tool version that `x-ga4gh-workflow` names, by
  its `primary_descriptor_path`
  (`.../PLAIN_{type}/descriptor/{path}`), so that relative imports of
  multi-file workflows resolve to files in TRS (see [Workflow URLs in
  TRS](../specification/engine-bindings.md#workflow-urls-in-trs)); without
  `primary_descriptor_path`, or if it starts with `/`, it is
  `.../PLAIN_{type}/descriptor`, which suits single-file workflows only.
  The tool doesn't read TRS: `primary_descriptor_path` must be the path
  exactly as TRS lists it. For CWL, the entry point becomes the fragment of
  the URL.

```bash
ga4gh-io-schema wes-params --schema workflow.schema.json --values values.json \
  --request --trs-url https://trs.example.org/ga4gh/trs/v2
```

The request is written as one JSON object; in the `multipart/form-data`
request of WES 1.1, `workflow_params` is sent as a JSON-encoded string.

Errors follow the [conventions](cli.md#conventions) of the command-line
interface: values that aren't valid, file references that break the rules
and bindings that can't be used are validation errors (exit status 1). The
location of an error in the values is the JSON path of the offending value
in the input values (e.g., `$.fastqs[1]`); errors of the schema itself say
so ("The schema doesn't comply with the GA4GH IO Profile: …") and name the
location in the schema. Where the schema has an `x-ga4gh-error-message` for
the failing value, the message is that text. Messages about file references
don't repeat the value.

## Python API

```python
from ga4gh_io_schema.wes import (
    build_run_request,
    to_workflow_params,
    trs_descriptor_url,
)

params = to_workflow_params(schema, values, allowed_schemes=["drs", "https", "s3"])
url = trs_descriptor_url(trs, tool_id, version_id, "WDL", "workflows/main.wdl")
request = build_run_request(schema, values, workflow_url=url)
```

A `TranslationError` names the location of the offending value both as a
JSON Pointer (`pointer`, e.g., `/fastqs/1`, as in the [test
vectors](../specification/engine-bindings.md#test-vectors)) and as a JSON
path (`json_path`, e.g., `$.fastqs[1]`, which the command-line interface
reports, like `validate`).

Reference of the API, generated from its docstrings:

::: ga4gh_io_schema.wes
