# WES request validation

The `wes-validate` subcommand of the [command-line interface](cli.md), and
`from_workflow_params()` of the `ga4gh_io_schema.wes` module, translate the
`workflow_params` of a GA4GH WES run request back into input values and
validate them against an IO schema, by the rules of [From `workflow_params`
back to input
values](../specification/engine-bindings.md#from-workflow_params-back-to-input-values).
They implement the conformance class [WES
server](../specification/conformance.md#wes-server) for the translation and
the validation; receiving the request, getting the schema from a trusted
source and answering over HTTP are left to the server. They are the reverse
of [`wes-params`](wes-params.md), and share its code for the binding and the
checks of file references.

## Command-line interface

```bash
ga4gh-io-schema wes-validate --schema workflow.schema.json --params workflow_params.json
```

The command:

1. validates the schema against the GA4GH IO Profile;
2. takes the engine binding from the schema's `x-ga4gh-workflow`;
3. matches each member of `workflow_params` with the input whose key it is
   (for WDL, `<entry_point>.<name>`); a member that matches no input keeps
   its name, so that the schema decides whether it is allowed (e.g., with
   `"additionalProperties": false`, it is rejected). A member whose name is
   that of an input bound to another key (e.g., a WDL key without the
   prefix) is rejected;
4. for CWL, turns each `File` or `Directory` object at a file reference
   into its `location`;
5. validates the values against `inputs`, and checks every value of a file
   reference against the rules of [Values](../specification/files.md#values)
   and the deployment's allow-list of schemes;
6. writes the input values, as indented JSON (with `--json`, on one line).

For the inputs of [Example 3](../specification/examples.md#example-3-workflow-bound-to-an-engine)
and these `workflow_params`:

```json
{
  "variant_calling.input_bam": "https://data.example.org/sample.bam",
  "variant_calling.sample_names": ["NA12878"],
  "variant_calling.call_variants.threads": 8
}
```

it writes:

```json
{
  "input_bam": "https://data.example.org/sample.bam",
  "sample_names": ["NA12878"],
  "caller_threads": 8
}
```

Options:

- `--descriptor-type`, `--type-version` and `--entry-point` fill in the
  fields of the binding that the schema lacks; a value that differs from the
  schema is an error. A server passes the request's `workflow_type` and
  `workflow_type_version` here, so that a request for another workflow
  language is rejected.
- `--allow-scheme SCHEME` (repeatable) and `--allow-absolute-paths` set the
  deployment's allow-list of URI schemes and whether absolute paths are
  accepted, as for [`wes-params`](wes-params.md#command-line-interface).
- `--allow-paths` accepts CWL `File` and `Directory` objects that give their
  file as `path` instead of `location`. The path is checked like any other
  file value.

CWL `File` and `Directory` objects are accepted only at file references
(their `class` must match the `kind`), and only with `class` and `location`
(or `path`): an object without them is invalid; `contents`, which would
carry the data of a file in the request, is rejected, and so are other
fields (e.g., `secondaryFiles` or `listing`, which would carry more files
past the checks; the runner finds secondary files next to the file). For
the other descriptor types, such objects are ordinary objects.

Errors follow the [conventions](cli.md#conventions) of the command-line
interface (a rejected request exits with status 1), except that the
location is the [JSON Pointer](https://www.rfc-editor.org/rfc/rfc6901) of
the offending value in `workflow_params`, as WES servers report it: its
first segment is the key of the member (e.g., `/variant_calling.input_bam`),
and that of a CWL file value ends with `/location`. The message is the
schema's `x-ga4gh-error-message` that covers the failure (see [Error
messages](../specification/keywords.md#error-messages)), or else is built
from the keyword that failed; it doesn't repeat the value. With `--json`,
the error also has the body of the WES `ErrorResponse` that a server
returns with `HTTP 400 Bad Request`, as `errorResponse`. For example, with
these `workflow_params`:

```json
{
  "variant_calling.input_bam": "file:///etc/passwd",
  "variant_calling.sample_names": ["NA12878"]
}
```

`--json` writes this error to standard error:

```json
{
  "error": {
    "kind": "validation",
    "message": "File references can't use the scheme 'file'.",
    "location": "/variant_calling.input_bam"
  },
  "errorResponse": {
    "msg": "/variant_calling.input_bam: File references can't use the scheme 'file'.",
    "status_code": 400
  },
  "exitCode": 1
}
```

An error of the request as a whole (e.g., a missing input, or a member that
`"additionalProperties": false` rejects) has no location; its `msg` starts
with `workflow_params:`.

## Python API

```python
from ga4gh_io_schema.wes import (
    WorkflowParamsError,
    error_response,
    from_workflow_params,
    get_binding,
)

binding = get_binding(
    schema,
    descriptor_type=request["workflow_type"],
    descriptor_type_version=request["workflow_type_version"],
)
try:
    values = from_workflow_params(
        schema, workflow_params, binding, allowed_schemes=["drs", "https", "s3"]
    )
except WorkflowParamsError as error:
    body = error_response(error)  # {"msg": …, "status_code": 400}
```

`get_binding()` raises a `TranslationError` for a binding that can't be
used (e.g., a `workflow_type` that differs from the schema, or `GALAXY`);
`error_response()` builds the body for it too. A `WorkflowParamsError` names
the location of the offending value in `workflow_params` as `pointer`. A
schema that doesn't comply with the profile raises
`jsonschema.exceptions.ValidationError`: it is an error of the deployment,
not of the request. The [test
vectors](../specification/engine-bindings.md#test-vectors) in
`tests/vectors/wes-requests/` give the expected values or error pointer for
each descriptor type.

The reference of the API is on the page [WES parameters](wes-params.md#python-api).
