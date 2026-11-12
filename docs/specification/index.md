# Specification

The GA4GH IO Schema Profile describes the inputs and outputs of workflows and
workflow components with JSON Schema (Draft 2020-12), extended with a set of
`x-ga4gh-*` keywords.

Requirements use the key words of BCP 14 (RFC 2119, RFC 8174), as
described in [Notational conventions](conformance.md#notational-conventions).

- [Keywords](keywords.md): the native JSON Schema keywords that the profile
  uses, tabular data, and the `x-ga4gh-*` vocabulary.
- [File references](files.md): how a string parameter refers to a file or
  a directory, its values, secondary files, and the mapping to the file types
  of CWL, WDL and nf-schema.
- [UI widgets](widgets.md): the input widgets and output viewers of
  `x-ga4gh-ui-widget`, the types and keywords that each one needs, and the
  values that input widgets produce.
- [Identity and engine binding](identity.md): how a schema names the
  workflow version and engine it describes, how clients detect drift, and
  how parameters bind to the engine's parameters.
- [Outputs](outputs.md): the outputs schema, the shapes of output values,
  and how clients find the outputs of a run in what a WES server returns.
- [Meta-schema](meta-schema.md): the meta-schema and vocabularies that
  schemas are validated against, and where they are served.
- [Conformance](conformance.md): the conformance classes (schema documents,
  validators, producers, clients and WES servers), their requirements, the
  conformance suite and the known implementations.
- [Examples](examples.md): a workflow and a single-step component.

The reasons for the design are in [Rationale](../rationale.md), and the
relation to other work in [Related work](../related-work.md).
