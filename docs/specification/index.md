# Specification

The GA4GH IO Schema Profile describes the inputs and outputs of workflows and
workflow components with JSON Schema (Draft 2020-12), extended with a set of
`x-ga4gh-*` keywords.

- [Keywords](keywords.md): the native JSON Schema keywords that the profile
  uses, tabular data, and the `x-ga4gh-*` vocabulary.
- [File references](files.md): how a string parameter refers to a file or
  a directory, its values, secondary files, and the mapping to the file types
  of CWL, WDL and nf-schema.
- [Outputs](outputs.md): the outputs schema, the shapes of output values,
  and how clients find the outputs of a run in what a WES server returns.
- [Meta-schema](meta-schema.md): the meta-schema and vocabularies that
  schemas are validated against, and where they are served.
- [Conformance](conformance.md): what schemas, servers and clients must do to
  conform to the profile.
- [Examples](examples.md): a workflow and a single-step component.

The reasons for the design are in [Rationale](../rationale.md), and the
relation to other work in [Related work](../related-work.md).
