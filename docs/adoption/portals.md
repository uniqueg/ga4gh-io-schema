# Portals and clients

## Data Repository Service (DRS) interplay

The `x-ga4gh-drs-uri` flag tells a client that an input expects a Data Repository Service (DRS) identifier. The client can then offer a DRS browser or picker, and check that the user can see the object, *before* submitting the run.

The client submits the `drs://` identifier itself in `workflow_params`, not a resolved access URL. The execution side resolves the identifier when it stages the data, with credentials delegated by the user. Signed URLs, access tokens and other credentials never go into `workflow_params`: WES returns them in the run log, they end up in engine logs and provenance records, and they can expire while the run is queued. See [Access to data](../security.md#access-to-data).

See also [the `x-ga4gh-*` vocabulary](../specification/keywords.md#the-x-ga4gh-vocabulary)
and the [output contract](../specification/outputs.md).

## Form libraries

IO schemas are JSON Schema 2020-12 documents, so generic JSON Schema form libraries can render forms for their standard keywords (types, enumerations, ranges, required properties). They don't understand the profile's `x-ga4gh-*` keywords, and some of them need configuration before they accept the schema at all:

- **Unknown keywords:** [Ajv](https://ajv.js.org/strict-mode.html), the validator used by many JavaScript form libraries, "fails schema compilation when unknown keywords are used" by default (strict mode). Portals register the `x-ga4gh-*` keywords (e.g., with `ajv.addKeyword`) or turn strict mode off.
- **Dialect:** some libraries default to an older dialect. For example, the default validator of react-jsonschema-form uses draft-07, and its [documentation](https://rjsf-team.github.io/react-jsonschema-form/docs/usage/validation/) notes that "`draft-2020-12` has breaking changes and hasn't been fully tested with `@rjsf`".
- **Profile keywords:** no form library reads `x-ga4gh-ui-widget`, `x-ga4gh-hidden` or the other `x-ga4gh-*` keywords. A portal needs an adapter that maps them to the library's own options (e.g., a UI schema or custom widgets). Widgets that the portal doesn't know are rendered by the parameter's type.

## AI agents

An IO schema can be the basis of a tool definition for an AI agent, e.g., the `inputSchema` and `outputSchema` of an [MCP tool](https://modelcontextprotocol.io/specification/2025-11-25/server/tools), whose default dialect is also JSON Schema 2020-12. The strict modes of LLM APIs, which constrain a model's output to a schema, accept only subsets of JSON Schema, and the subsets differ:

- [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs) require `additionalProperties: false` and every property to be `required`, and don't support the `uri` format.
- [Anthropic structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) don't support numeric constraints such as `minimum` and `maximum`, string length constraints, or external `$ref`.

A tool definition derived from an IO schema therefore drops or rewrites what the target API doesn't support (e.g., moves constraints into descriptions) and keeps validating the values against the full IO schema. Constrained decoding guarantees the *shape* of the arguments, not that they are correct for the analysis.

## Guide for portals and clients

> **To be written.** This section will describe, step by step, how portals,
> other clients and AI agents render input forms from an IO schema, use the
> UI hints, and interpret the outputs of a run.
