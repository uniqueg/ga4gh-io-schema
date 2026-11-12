# Specification

The GA4GH IO Schema Profile describes the inputs and outputs of workflows and
workflow components with JSON Schema (Draft 2020-12), extended with a set of
`x-ga4gh-*` keywords.

Requirements use the key words of BCP 14 (RFC 2119, RFC 8174), as
described in [Notational conventions](conformance.md#notational-conventions).

- [Keywords](keywords.md): the native JSON Schema keywords that the profile
  uses, tabular data, and the `x-ga4gh-*` vocabulary.
- [Output contract](outputs.md): how clients match the outputs of a schema
  with the outputs of a run.
- [Meta-schema](meta-schema.md): the meta-schema and vocabularies that
  schemas are validated against, and where they are served.
- [Conformance](conformance.md): the conformance classes (schema documents,
  validators, producers, clients and WES servers), their requirements, the
  conformance suite and the known implementations.
- [Examples](examples.md): a workflow and a single-step component.

The reasons for the design are in [Rationale](../rationale.md), and the
relation to other work in [Related work](../related-work.md).
