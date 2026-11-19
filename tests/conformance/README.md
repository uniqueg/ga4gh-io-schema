# Conformance suite

Language-neutral test cases of the GA4GH IO Schema Profile, for any
implementation:

- `schema-documents/valid/*.schema.json`: a validator MUST accept each.
- `schema-documents/invalid/*.schema.json`: a validator MUST reject each;
  each breaks the rule that its file name names (a few also break others).

Apart from the cases about `$schema` (`foreign-schema`, `missing-schema`,
`empty`, `plain-json-schema`), the cases name the profile's meta-schema by
its versioned `$id` in `$schema`; load it and its vocabularies from
`schemas/`, not from the network. Error messages are not part of the suite. `*.license` files hold
licence information and are not cases.

The requirements, and how this package runs the suite, are described in the
[Conformance](https://ga4gh-io-schema.readthedocs.io/en/latest/specification/conformance/#conformance-suite)
page of the documentation.
