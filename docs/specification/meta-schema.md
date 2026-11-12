# Meta-schema

IO schemas are validated against the GA4GH IO Profile meta-schema, a JSON
Schema (Draft 2020-12) of the repository:

- [`schemas/ga4gh-io-profile.schema.json`](https://github.com/uniqueg/ga4gh-io-schema/blob/main/schemas/ga4gh-io-profile.schema.json):
  the meta-schema, with the [`x-ga4gh-*` keywords](keywords.md#the-x-ga4gh-vocabulary).
- [`schemas/vocabularies/ui-widgets.schema.json`](https://github.com/uniqueg/ga4gh-io-schema/blob/main/schemas/vocabularies/ui-widgets.schema.json):
  the vocabulary of UI widgets (values of `x-ga4gh-ui-widget`).

The [validator](../tools/validator.md) checks schemas against them.

## Referencing the meta-schema

Inside your own drafted schemas, you can reference the meta-schema directly to enable IDE autocompletion and validation. The identifier is
versioned: it names a release of the profile, not a moving branch. Replace the
`$id` of the example with an identifier of your own.

```json
{
  "$schema": "https://raw.githubusercontent.com/uniqueg/ga4gh-io-schema/v0.3.0/schemas/ga4gh-io-profile.schema.json",
  "$id": "https://example.org/schemas/my-tool/v1"
}
```

## Where the meta-schema is served

As a schema standard, there is no active deployment of a service. The schemas and vocabularies are served statically via raw GitHub URLs. In the future, the goal is to integrate this schema format natively into **TRS (Tool Registry Service)** implementations as a new `IO_SCHEMA` file type (see [TRS](../adoption/trs.md)).

## Structure of the meta-schema

> **To be written.** This section will describe the structure of the
> meta-schema keyword by keyword: the required top-level properties
> (`inputs`, `outputs`), where the `x-ga4gh-*` keywords may appear, and how
> vocabularies are referenced and versioned.
