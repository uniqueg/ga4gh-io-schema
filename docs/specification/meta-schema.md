# Meta-schema

IO schemas are validated against the GA4GH IO Profile meta-schema, a JSON
Schema (Draft 2020-12) of the repository:

- [`schemas/ga4gh-io-profile.schema.json`](https://github.com/uniqueg/ga4gh-io-schema/blob/main/schemas/ga4gh-io-profile.schema.json):
  the meta-schema: the rules for the top level of an IO schema, and (in
  `$defs/node`) the rules for every schema of an IO schema, at any depth,
  which combine the vocabularies.
- [`schemas/vocabularies/annotations.schema.json`](https://github.com/uniqueg/ga4gh-io-schema/blob/main/schemas/vocabularies/annotations.schema.json):
  the [`x-ga4gh-*` keywords](keywords.md#the-x-ga4gh-vocabulary) that annotate
  parameters for clients (UI hints, error message, description format,
  ontology term).
- [`schemas/vocabularies/file.schema.json`](https://github.com/uniqueg/ga4gh-io-schema/blob/main/schemas/vocabularies/file.schema.json):
  the `x-ga4gh-*` keywords of file parameters ([file
  references](files.md), tabular files).
- [`schemas/vocabularies/parameter.schema.json`](https://github.com/uniqueg/ga4gh-io-schema/blob/main/schemas/vocabularies/parameter.schema.json):
  the binding of a parameter to the engine's parameter (`x-ga4gh-parameter`).
- [`schemas/vocabularies/workflow.schema.json`](https://github.com/uniqueg/ga4gh-io-schema/blob/main/schemas/vocabularies/workflow.schema.json):
  the top-level keywords: the workflow version and engine of the schema
  (`x-ga4gh-workflow`, see [Identity and engine binding](identity.md)).
- [`schemas/vocabularies/outputs.schema.json`](https://github.com/uniqueg/ga4gh-io-schema/blob/main/schemas/vocabularies/outputs.schema.json):
  the `x-ga4gh-*` keywords that find the outputs of a run
  ([Outputs](outputs.md)).
- [`schemas/vocabularies/ui-widgets.schema.json`](https://github.com/uniqueg/ga4gh-io-schema/blob/main/schemas/vocabularies/ui-widgets.schema.json):
  the vocabulary of UI widgets (values of `x-ga4gh-ui-widget`), and the
  rules for the schemas that each widget fits (see [UI widgets](widgets.md)).

The [validator](../tools/validator.md) checks schemas against them.

## Referencing the meta-schema

Inside your own drafted schemas, you can reference the meta-schema directly to
enable IDE autocompletion and validation. The identifier is versioned: it names
a release of the profile, not a moving branch. Use the tag of the profile
release that you target, and replace the `$id` of the example with an
identifier of your own.

```json
{
  "$schema": "https://raw.githubusercontent.com/uniqueg/ga4gh-io-schema/v0.3.0/schemas/ga4gh-io-profile.schema.json",
  "$id": "https://example.org/schemas/my-tool/v1"
}
```

## Dialect and validation of values

The meta-schema declares its vocabularies in `$vocabulary`, so that it is a
dialect of JSON Schema Draft 2020-12: the vocabularies of Draft 2020-12
(core, applicator, unevaluated, validation, meta-data, format-annotation,
content) are required, as in the Draft 2020-12 meta-schema, and the
profile's own vocabulary (an identifier, not a document; see `$vocabulary`
in the meta-schema) is optional, so that validators that don't know it
still process IO schemas.

Input values (e.g., the `workflow_params` of a WES request) are validated
against `properties.inputs` of the IO schema, and normalised outputs against
`properties.outputs`, with the semantics of Draft 2020-12:

- The `x-ga4gh-*` keywords are annotations: they MUST NOT change whether a
  value is valid. Their rules for values (e.g., the value syntax of [file
  references](files.md#values)) are checked separately, where this
  specification says so.
- A validator MAY use the dialect of the profile (the `$schema` of the IO
  schema) or the Draft 2020-12 dialect; the choice of dialect MUST NOT
  change the result. A client that uses the Draft 2020-12 dialect MUST
  first validate the IO schema against the profile, and then MAY validate
  values against a copy of the IO schema in which every `$schema` that
  names the profile (at the root and in embedded resources) names Draft
  2020-12 (`https://json-schema.org/draft/2020-12/schema`) instead. [JavaScript
  validators](../tools/javascript.md#validating-input-values) describes
  validators that need this.
- `format` is an annotation in Draft 2020-12. A request builder SHOULD
  assert `format` on values for the formats that its validator supports
  (e.g., `date` for date widgets). Validators differ in the formats they
  support and in how strictly they check them, so a WES server MUST NOT
  rely on a client's check of `format`.
- References in `inputs` (e.g., to the `$defs` of the IO schema) MUST
  resolve against the IO schema; a validator that follows them validates
  against `inputs` in place, e.g., by the URI
  `<base URI>#/properties/inputs`, where the base URI is the `$id` of the
  IO schema or, without one, a URI that the client assigns (e.g., its
  retrieval URL).

## Where the meta-schema is served

As a schema standard, there is no active deployment of a service. The schemas and vocabularies are served statically via raw GitHub URLs, at the release tag that their `$id`s name. IO schemas of workflows are published in **TRS (Tool Registry Service)** implementations as files of the existing type `OTHER` (see [TRS](../adoption/trs.md)); a dedicated file type such as `IO_SCHEMA` is deferred (see [Roadmap](../roadmap.md#deferred)).

## Structure of the meta-schema

The meta-schema has two parts.

**Top level** (`ga4gh-io-profile.schema.json`): an IO schema is a JSON object
that

- names the meta-schema in `$schema`, by its versioned `$id`;
- has an absolute URI as `$id`, if it sets `$id`, and not the URL of a
  branch (see [Identifiers and
  versions](identity.md#identifiers-and-versions));
- has `"type": "object"`, if it sets `type`;
- has `properties` with the wrapper of the parameters: `inputs` (required),
  the JSON Schema of the inputs, and `outputs` (optional), the JSON Schema of
  the outputs: an object schema without references or applicators, with
  `"type": "object"` if it sets `type`
  (see [Outputs](outputs.md#the-outputs-schema));
- may carry the top-level keywords of `vocabularies/workflow.schema.json`
  (`x-ga4gh-workflow`), which are allowed only there.

**Every schema, at any depth** (`$defs/node` of `ga4gh-io-profile.schema.json`,
with the Draft 2020-12 meta-schema applied once per tree, see below):
the top level and every nested schema (e.g., in `properties`, `items`,
`$defs`, and `x-ga4gh-tabular-schema`) MUST be valid JSON Schema Draft
2020-12 and MUST use the `x-ga4gh-*` keywords as defined in
[Keywords](keywords.md).
The rules combine one vocabulary file per keyword group:

| Keyword | Value | Vocabulary |
| ----- | ----- | ----- |
| `x-ga4gh-ontology` | string, a URI | `annotations` |
| `x-ga4gh-ui-widget` | a widget of the [vocabulary](https://github.com/uniqueg/ga4gh-io-schema/blob/main/schemas/vocabularies/ui-widgets.schema.json), or `custom:<name>` (lowercase letters, digits and hyphens); a widget of the vocabulary needs the type and keywords that it fits in the same schema, and viewers are for outputs (see [UI widgets](widgets.md)) | `annotations`, `ui-widgets` |
| `x-ga4gh-description-format` | `plain_text` or `markdown` | `annotations` |
| `x-ga4gh-hidden` | boolean | `annotations` |
| `x-ga4gh-error-message` | string | `annotations` |
| `x-ga4gh-file` | an object with `kind` (`file` or `directory`) and optional `mediaType`, `ontology`, `compression`, `secondaryFiles` and `schemes` (see [File references](files.md)); the schema that carries it is a flat string schema (see [The annotation](files.md#the-annotation)) | `file` |
| `x-ga4gh-tabular-schema` (experimental) | a schema, checked by the same rules | `file` |
| `x-ga4gh-parameter` | object with `name` and `type` (strings, at least one) | `parameter` |
| `x-ga4gh-workflow` | object, see [The workflow block](identity.md#the-workflow-block); top level only | `workflow` |
| `x-ga4gh-output-glob` | a relative glob (see [`x-ga4gh-output-glob`](outputs.md#x-ga4gh-output-glob)), on a file reference or on an array whose `items` is a file reference written in place, without `prefixItems` | `outputs` |

Other keywords that start with `x-ga4gh-` (e.g., misspelled ones, or
`x-ga4gh-fa-icon`, which version 0.3 removed) are rejected: no vocabulary evaluates them, and `$defs/node` doesn't allow
unevaluated `x-ga4gh-*` keywords. Other extension keywords (e.g.,
`x-my-platform-hint`) are allowed. A new keyword group goes into a new file
in `schemas/vocabularies/`, referenced from `$defs/node/$defs/keywords`
(keywords of every schema) or from the branch of the top level's `allOf`
that checks the `x-ga4gh-*` keywords (top-level keywords). The rule marks
other keywords as evaluated with the pattern `^(?!x-ga4gh-)`, a negative
lookahead: valid ECMA-262, and supported by the common validators of Python
and JavaScript, but not by validators built on RE2 (e.g., Go's `regexp`).

The rules reach nested schemas through explicit `$ref`s:
`$defs/node/$defs/subschemas` applies `$defs/node` to the value of every
keyword whose value is a schema or holds schemas (the applicators of Draft
2020-12, e.g., `properties`, `items`, `allOf` and `$defs`, the deprecated
`definitions` and `dependencies`, and `x-ga4gh-tabular-schema`). The
Draft 2020-12 meta-schema checks every subschema against plain JSON Schema:
it is applied once per tree of schemas (`$defs/node/$defs/schema`), to the
top level and to each `x-ga4gh-tabular-schema`, which its applicators don't
reach, and from there checks every schema nested in it. The meta-schema
uses no `$dynamicRef` or `$dynamicAnchor`, because some validators (e.g.,
Ajv) support them only at the root of a schema and would skip the rules for
nested schemas without an error (see [JavaScript
validators](../tools/javascript.md)).

The top level uses the rules of `$defs/node` (`$defs/node/$defs/schema` and
`$defs/node/$defs/keywords`) without its check of unevaluated keywords, adds
the top-level keywords, and rejects other `x-ga4gh-*` keywords with its own
check: a check of unevaluated keywords only sees the keywords evaluated in
its own schema and the subschemas it applies, so the check of `$defs/node`
would reject the top-level keywords.

The structure keeps validation time roughly linear in the size of the
schema. Each check of unevaluated keywords sits in an `allOf` branch of its
own and sees only the vocabularies (`$defs/node/$defs/keywords`), none of
which reaches a nested schema; the rules for nested schemas are in another
branch. Some validators (e.g., Python's `jsonschema`) evaluate the
subschemas that a check of unevaluated keywords sees once more, to collect
their annotations; if the check saw the rules for nested schemas, each level
would validate all levels below it again, in time exponential in the depth
of nesting. For the same reason, `$defs/node` doesn't apply the Draft
2020-12 meta-schema itself: applied to every schema, it would check each
schema once for each of its ancestors. Changes of the meta-schema keep this
structure (`tests/test_packaging.py` and `tests/test_meta_schema.py` check
it).

The `$ref`s between the schemas use the versioned `$id`s; the validator
resolves them from the copies that the package ships and never fetches them
from the network.
