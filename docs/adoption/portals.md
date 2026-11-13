# Portals and clients

This guide is for portals, other clients and AI agents that render input
forms from IO schemas, build run requests and show the outputs of runs. It
is informative: the requirements are those of the conformance classes
[Form renderer](../specification/conformance.md#form-renderer),
[Request builder](../specification/conformance.md#request-builder) and
[Output normaliser](../specification/conformance.md#output-normaliser), and
of [Security considerations](../security.md), which govern where this page
repeats them.

## Guide for portals and clients

A client goes through these steps, from the schema to the run request:

1. [Fetch the schema from TRS](#1-fetch-the-schema-from-trs).
2. [Check the workflow block](#2-check-the-workflow-block) against the tool
   version, and warn on drift.
3. [Validate the schema offline](#3-validate-the-schema-offline).
4. [Render the inputs](#4-render-the-inputs) by type and widget, with
   fallbacks.
5. [Render text and Markdown](#5-render-text-and-markdown) under the
   security rules.
6. [Check file reference values](#6-check-file-reference-values): schemes,
   allow-list, paths.
7. [Validate the values](#7-validate-the-values).
8. [Hand the values to a request builder](#8-hand-the-values-to-a-request-builder).

After the run, it [shows the outputs](#after-the-run-outputs).

### 1. Fetch the schema from TRS

Find the IO schema of the tool version as described in
[Discovery by clients](trs.md#discovery-by-clients): the file of type
`OTHER` with the path `ga4gh-io.schema.json` next to the primary descriptor
of the descriptor type that the client wants to run. Keep the URL that the
schema came from: it is the base URI of a schema without `$id` (see step
7). Keep also the checksum of the primary descriptor (`FileWrapper.checksum`)
for step 2.

The schema comes from the author of the workflow, through a registry: the
client treats its text as untrusted (see step 5). A tool version without an
IO schema gets what the client offers without the profile, e.g., a plain
JSON editor for the parameters.

### 2. Check the workflow block

`x-ga4gh-workflow` ties the schema to a workflow version (see
[The workflow block](../specification/identity.md#the-workflow-block)).
Before the client uses the schema, it compares:

- `trs_tool_id`, `trs_version_id` and `descriptor_type`, where the schema
  has them, with the tool version and descriptor type that it fetched the
  schema for;
- the `checksum` of the primary descriptor with the checksum from TRS, or
  with one that it computes over the descriptor, for an algorithm that it
  supports (see [Drift](../specification/identity.md#drift)).

On a mismatch, the client doesn't use the schema silently: it refuses the
schema, or it shows a warning next to the form that the schema may not
match the workflow. A schema that the client can't check (no checksum, no
supported algorithm, no access to the descriptor) is unverified; the client
may use it, and may say so.

### 3. Validate the schema offline

Check the schema against the [meta-schema](../specification/meta-schema.md)
of a profile version that the client supports, as a
[Validator](../specification/conformance.md#validator) does, before
rendering anything:

- **Offline:** load the meta-schema and its vocabularies from copies bundled
  with the client, and never retrieve a reference over the network, also
  not in a browser (see [Sources of schemas](../security.md#sources-of-schemas)).
  Validators that fetch unknown `$ref`s by default must have that turned
  off: @hyperjump/json-schema retrieves them over HTTP(S) unless the
  client removes its `http` and `https` URI scheme plugins.
- **`$schema`:** the schema must name a supported version of the profile
  in `$schema`; a schema without it, or with another meta-schema, is
  rejected.
- **Formats:** turn on format assertion (e.g., ajv-formats for Ajv), or
  the client accepts schemas with, for example, an `x-ga4gh-ontology` that
  isn't a URI.
- **Failures:** don't render a form from a schema that fails, or that has
  references that the client can't resolve from the schema itself and its
  local copies.

[JavaScript validators](../tools/javascript.md) has a runnable setup for
Ajv and @hyperjump/json-schema, and their
[results](../tools/javascript.md#results) on the
[conformance suite](../specification/conformance.md#conformance-suite):
with that setup, both accept every valid and reject every invalid case. A
portal with a Python backend can use the
[Python validator](../tools/validator.md) instead.

### 4. Render the inputs

Render one control for every property of `inputs`, at any depth: a group
for each object, a list editor for each array. Every input must be
settable.

**Widgets.** If the schema has an `x-ga4gh-ui-widget` that the client knows
and that fits the schema (see [Input widgets](../specification/widgets.md#input-widgets)),
render that widget, and produce the values that the table there defines
(e.g., `#rrggbb` for a `color-picker`, an array of strings for `tags`).
Otherwise, render the input as an input of the same type without a widget:
a widget that the client doesn't know (e.g., `custom:` of another
platform), an output viewer on an input, and a widget that doesn't fit its
schema are ignored (see [Rules](../specification/widgets.md#rules)).

**Fallbacks.** Without a widget, choose the control by `type`, `format` and
`enum`, for example:

| Schema | Control |
| ----- | ----- |
| `enum` | A dropdown or radio buttons of the values |
| `boolean` | A checkbox |
| `integer`, `number` | A number field, with the bounds of the schema |
| `string` with `format` `date`, `time` or `date-time` | A date, time or date-time picker |
| `string` with `x-ga4gh-file` | A file picker (`"kind": "file"`) or directory picker (`"kind": "directory"`) that offers the sources of `schemes`, e.g., a DRS browser for `drs` (see [Clients](../specification/files.md#clients)) |
| other `string` | A text field |
| `array` | A list editor, with a control for the `items` |
| `object` | A group of controls, one per property |

**Defaults.** A form may prefill the `default` of an input; a prefilled
value is a value that the user sets, and is sent (see
[Engine bindings](../specification/engine-bindings.md#from-input-values-to-workflow_params)).
Inputs that the user leaves unset are left out of the values, not sent as
`null`. The `default`, `const`, `enum` and `examples` of a file reference
are file reference values: check them as in step 6 before prefilling or
showing them.

**Hidden inputs.** `"x-ga4gh-hidden": true` lets a form show an input only
on request, e.g., under "Advanced" (see
[Hidden inputs](../specification/keywords.md#hidden-inputs)), with two
exceptions:

- An input that users must set is shown with the other inputs, as if it
  weren't hidden. It must be set if it is in `required` of its object and
  no `default` gives it a value, neither its own nor one of an enclosing
  schema; inside an optional object, once the object is set.
- A hidden input whose value fails validation is shown, with its error.

For example, the form shows `reference` with the other inputs, although it
is hidden, and `threads` only on request:

```json
{
  "type": "object",
  "properties": {
    "reference": {
      "type": "string",
      "x-ga4gh-file": {"kind": "file"},
      "x-ga4gh-hidden": true
    },
    "threads": {"type": "integer", "default": 4, "x-ga4gh-hidden": true}
  },
  "required": ["reference"]
}
```

Schema documents shouldn't hide inputs that must be set, but the
meta-schema can't reject them, so a form has to check.

**Unions with a file reference.** A CWL input of type `[File, string]`
becomes `anyOf` with a file reference and a plain string as its branches
(see [Mapping to workflow languages](../specification/files.md#mapping-to-workflow-languages)):

```json
{
  "anyOf": [
    {"type": "string", "x-ga4gh-file": {"kind": "file"}},
    {"type": "string"}
  ]
}
```

Every string is valid against the file reference branch, so every value of
this input is a file reference value: it is checked as one (step 6), and
the request builder sends it as the engine takes files (for CWL, a `File`
object), even if the user meant plain text (see
[Values](../specification/files.md#values)). Render such an input as a
file picker that also takes a typed value, not as a choice between "file"
and "text", which would suggest that text is sent as text. Where the
branches have different types (e.g., `[File, int]`), let the user choose
the branch, and render the control of the chosen branch. With `oneOf`
instead of `anyOf`, a string that is valid against both branches fails,
because `oneOf` allows exactly one; converters use `anyOf`.

**Error messages.** When a value fails validation (step 7), show the
`x-ga4gh-error-message` that covers the failure, if there is one, next to
the input, in place of the validator's message; the rules for which
message covers which failure are in
[Error messages](../specification/keywords.md#error-messages). Offer the
validator's message on request, e.g., for authors of schemas.

### 5. Render text and Markdown

`title`, `description`, the values of `enum` and `x-ga4gh-error-message`
come from the author of the schema; show them as text, never as HTML (see
[Rendering schemas and outputs](../security.md#rendering-schemas-and-outputs)).

With `"x-ga4gh-description-format": "markdown"`, render the description as
defined in [Markdown descriptions](../specification/keywords.md#markdown-descriptions),
or show it as plain text:

- raw HTML comes out as text (e.g., `html: false` of markdown-it);
- images come out as their alt text, without being loaded: replace the
  library's renderer for images, because turning images off can make a
  library show them as links;
- links are links only if their destination is an absolute URI with a
  scheme on the client's allow-list; others come out as their link text.

With these rules, a description needs no HTML sanitiser. Descriptions in
any other format are plain text.

### 6. Check file reference values

Check every value where a file reference applies, before submitting the
run, by the rules of [Values](../specification/files.md#values) and
[URIs and file references](../security.md#uris-and-file-references). JSON
Schema validators don't check them (step 7 doesn't replace this step):

- **Schemes:** a URI's scheme must be on the deployment's allow-list and,
  where the file reference has `schemes`, in `schemes` too. `javascript`,
  `data` and other schemes that run code in a browser are never on the
  allow-list.
- **Paths:** values without a scheme are paths, allowed only for inputs
  whose file reference has no `schemes`. A relative path names a file
  attached to the run request (`workflow_attachment`); absolute paths only
  work in deployments with a shared file system. Reject paths with `..`
  segments (also percent-encoded), paths that start with `~`, `//` or
  `\\`, control characters, and leading or trailing whitespace.
- **DRS:** submit `drs://` identifiers as they are, not resolved access
  URLs, and never put signed URLs, tokens or other credentials into the
  values (see [Data Repository Service (DRS) interplay](#data-repository-service-drs-interplay)).

The `file-values` [test vectors](../specification/engine-bindings.md#test-vectors)
give the decision for each kind of value. A WES server checks the values
again: the checks of a client save a failed run, they don't protect the
server (see [Validation is not a security boundary](../security.md#validation-is-not-a-security-boundary)).

### 7. Validate the values

Validate the values against `inputs` of the schema, with the semantics of
Draft 2020-12, as [Dialect and validation of values](../specification/meta-schema.md#dialect-and-validation-of-values)
defines:

- Validate against `<base URI>#/properties/inputs`, so that references to
  the `$defs` of the schema resolve; the base URI is the `$id` of the
  schema or, without one, a URI that the client chooses, such as the URL
  that it fetched the schema from (step 1).
- The `x-ga4gh-*` keywords are annotations: they don't change the result.
- Assert `format` on values for the formats that the validator supports
  (e.g., `date` for a date picker).
- Don't submit values that fail; show the errors as in step 4.

The validators need different setups for this, which
[Validating input values](../tools/javascript.md#validating-input-values)
gives: Ajv uses a second instance, to which the profile is added as a
meta-schema; @hyperjump/json-schema validates against a copy of the schema
whose `$schema` names Draft 2020-12, because it rejects schemas that name
the profile as their dialect.

### 8. Hand the values to a request builder

A [Request builder](../specification/conformance.md#request-builder)
translates the values into the `workflow_params` of the schema's
descriptor type and builds the WES run request, as
[Engine bindings](../specification/engine-bindings.md) defines:

- parameter names from `x-ga4gh-parameter`, qualified with the entry point
  for WDL; file values as the engine takes them (CWL `File` and `Directory`
  objects); no `default`s inserted; values with colliding names rejected;
- `workflow_type`, `workflow_type_version` and `workflow_url` from
  `x-ga4gh-workflow` and TRS, and the files of relative paths in
  `workflow_attachment` (see [Run requests](../specification/engine-bindings.md#run-requests));
- schemas whose descriptor type has no binding (`GALAXY` in version 0.3)
  are rejected.

The [`wes-params`](../tools/wes-params.md) tool and its Python API do the
checks of step 6 and this translation (not the submission), e.g., in the
backend of a portal. A client with an implementation of its own checks it
against the `wes-params` test vectors. See also
[Building run requests](wes.md#building-run-requests-clients).

### After the run: outputs

An [Output normaliser](../specification/conformance.md#output-normaliser)
matches the outputs of the run with `outputs` of the schema, into the
[normalised outputs object](../specification/outputs.md#the-normalised-outputs-object),
and shows them:

- check the scheme of every output reference against the allow-list before
  showing it as a link or loading it into a viewer;
- show an `html-viewer` output only in a sandboxed `iframe` with a Content
  Security Policy, escape the cells of a `table-viewer`, and offer every
  other output for download only (see
  [Rendering schemas and outputs](../security.md#rendering-schemas-and-outputs));
- show the outputs of a run that didn't complete as partial (see
  [Runs that don't complete](../specification/outputs.md#runs-that-dont-complete)).

The [output normaliser](../tools/outputs.md) of the `ga4gh-io-schema`
package builds the normalised outputs object from a WES run log.

### Reference client

No client implements the profile yet. ELIXIR Cloud Components plans
elements that render input forms, build run requests and show outputs from
IO schemas (see [Implementations](../specification/conformance.md#implementations)).
The [End-to-end demo](demo.md#3-run-it-from-a-portal) lists what a portal
should show for its workflow, as a check for a client.

## Data Repository Service (DRS) interplay

A [file reference](../specification/files.md) whose `schemes` include `drs` tells a client that an input accepts a Data Repository Service (DRS) identifier (`"x-ga4gh-file": {"kind": "file", "schemes": ["drs"]}`). The client can then offer a DRS browser or picker, and check that the user can see the object, *before* submitting the run.

The client submits the `drs://` identifier itself in `workflow_params`, not a resolved access URL, and no credentials; the execution side resolves the identifier with credentials delegated by the user. See [Access to data](../security.md#access-to-data) for the requirements and the reasons.

See also [the `x-ga4gh-*` vocabulary](../specification/keywords.md#the-x-ga4gh-vocabulary)
and the [outputs model](../specification/outputs.md).

## Form libraries

IO schemas are JSON Schema 2020-12 documents, so generic JSON Schema form libraries can render forms for their standard keywords (types, enumerations, ranges, required properties). They don't understand the profile's `x-ga4gh-*` keywords, and some of them need configuration before they accept the schema at all:

- **Unknown keywords:** [Ajv](https://ajv.js.org/strict-mode.html), the validator used by many JavaScript form libraries, "fails schema compilation when unknown keywords are used" by default (strict mode). Registering the `x-ga4gh-*` keywords (e.g., with `ajv.addKeyword`) isn't enough: the profile also allows other keywords, such as the `x-` keywords of a platform (e.g., `x-my-platform-hint`), and Ajv allows unknown keywords only by their exact names. Clients that compile IO schemas with Ajv need `strictSchema: false` (or `strict: false`).
- **Content Security Policy:** Ajv compiles schemas into JavaScript functions with `new Function`, so the page's Content Security Policy must allow `'unsafe-eval'` (see [Ajv's security notes](https://ajv.js.org/security.html)). Precompiling the validation functions at build time doesn't help, because IO schemas arrive at runtime, from TRS. @hyperjump/json-schema doesn't compile with `new Function` and needs no `'unsafe-eval'`.
- **Network:** validators that fetch unknown `$ref`s by default (e.g., @hyperjump/json-schema, over HTTP(S)) must have that turned off, also in browsers (see [step 3](#3-validate-the-schema-offline)).
- **Dialect:** some libraries default to an older dialect. For example, the default validator of react-jsonschema-form uses draft-07, and its [documentation](https://rjsf-team.github.io/react-jsonschema-form/docs/usage/validation/) notes that "`draft-2020-12` has breaking changes and hasn't been fully tested with `@rjsf`".
- **Profile keywords:** no form library reads `x-ga4gh-ui-widget`, `x-ga4gh-hidden` or the other `x-ga4gh-*` keywords. A portal needs an adapter that maps them to the library's own options (e.g., a UI schema or custom widgets), and that applies the rules of [step 4](#4-render-the-inputs), e.g., for hidden inputs that must be set. Widgets that the portal doesn't know are rendered by the parameter's type.

The [results](../tools/javascript.md#results) of Ajv 8.20.0 and @hyperjump/json-schema 1.18.0 on the conformance suite, with the setups of [JavaScript validators](../tools/javascript.md), are the same as those of the Python validator; the page also lists where they differ outside the suite.

## AI agents

An IO schema can be the basis of a tool definition for an AI agent, e.g., the `inputSchema` and `outputSchema` of an [MCP tool](https://modelcontextprotocol.io/specification/2025-11-25/server/tools), whose default dialect is also JSON Schema 2020-12. The strict modes of LLM APIs, which constrain a model's output to a schema, accept only subsets of JSON Schema, and the subsets differ:

- [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs) require `additionalProperties: false` and every property to be `required`, and don't support the `uri` format.
- [Anthropic structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) don't support numeric constraints such as `minimum` and `maximum`, string length constraints, or external `$ref`.

A tool definition derived from an IO schema therefore drops or rewrites what the target API doesn't support (e.g., moves constraints into descriptions) and keeps validating the values against the full IO schema. Constrained decoding guarantees the *shape* of the arguments, not that they are correct for the analysis. The steps of the [guide](#guide-for-portals-and-clients) apply to agents as to forms: an agent checks the schema (steps 1 to 3), shows text as text (step 5), and checks the file reference values and the values (steps 6 and 7) before it hands them to a request builder.
