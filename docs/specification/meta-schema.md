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
  the `x-ga4gh-*` keywords of file parameters (DRS URIs, tabular files).
- [`schemas/vocabularies/ui-widgets.schema.json`](https://github.com/uniqueg/ga4gh-io-schema/blob/main/schemas/vocabularies/ui-widgets.schema.json):
  the vocabulary of UI widgets (values of `x-ga4gh-ui-widget`).

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

## Where the meta-schema is served

As a schema standard, there is no active deployment of a service. The schemas and vocabularies are served statically via raw GitHub URLs. In the future, the goal is to integrate this schema format natively into **TRS (Tool Registry Service)** implementations as a new `IO_SCHEMA` file type (see [TRS](../adoption/trs.md)).

## Structure of the meta-schema

The meta-schema has two parts.

**Top level** (`ga4gh-io-profile.schema.json`): an IO schema is a JSON object
that

- names the meta-schema in `$schema`, by its versioned `$id`;
- has `"type": "object"`, if it sets `type`;
- has `properties` with the wrapper of the parameters: `inputs` (required),
  the JSON Schema of the inputs, and `outputs` (optional), the JSON Schema of
  the outputs.

**Every schema, at any depth** (`$defs/node` of `ga4gh-io-profile.schema.json`):
the top level and every nested schema (e.g., in `properties`, `items`,
`$defs`, and `x-ga4gh-tabular-schema`) must be valid JSON Schema Draft
2020-12 and use the `x-ga4gh-*` keywords as defined in [Keywords](keywords.md).
The rules combine one vocabulary file per keyword group:

| Keyword | Value | Vocabulary |
| ----- | ----- | ----- |
| `x-ga4gh-ontology` | string, a URI | `annotations` |
| `x-ga4gh-ui-widget` | a widget of the [vocabulary](https://github.com/uniqueg/ga4gh-io-schema/blob/main/schemas/vocabularies/ui-widgets.schema.json), or `custom:<name>` | `annotations` |
| `x-ga4gh-fa-icon` | string | `annotations` |
| `x-ga4gh-description-format` | `plain_text`, `markdown` or `rst` | `annotations` |
| `x-ga4gh-hidden` | boolean | `annotations` |
| `x-ga4gh-error-message` | string | `annotations` |
| `x-ga4gh-drs-uri` | boolean | `file` |
| `x-ga4gh-tabular-schema` | a schema, checked by the same rules | `file` |

Other keywords that start with `x-ga4gh-` (e.g., misspelled ones) are
rejected: no vocabulary evaluates them, and `$defs/node` doesn't allow
unevaluated `x-ga4gh-*` keywords. Other extension keywords (e.g.,
`x-my-platform-hint`) are allowed. A new keyword group goes into a new file
in `schemas/vocabularies/`, referenced from `$defs/node`. The rule marks
other keywords as evaluated with the pattern `^(?!x-ga4gh-)`, a negative
lookahead: valid ECMA-262, and supported by the common validators of Python
and JavaScript, but not by validators built on RE2 (e.g., Go's `regexp`).

The rules reach nested schemas through the `$dynamicAnchor` mechanism of
Draft 2020-12: `$defs/node` declares `"$dynamicAnchor": "meta"`, so the
applicators of the Draft 2020-12 meta-schema apply it, not plain JSON
Schema, to every subschema. The top-level rules don't declare the anchor, so
they apply only to the top level. The `$ref`s between the schemas use the
versioned `$id`s; the validator resolves them from the copies that the
package ships and never fetches them from the network.
