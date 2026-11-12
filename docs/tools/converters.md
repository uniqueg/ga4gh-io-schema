# Converters

> **To be written.** Converters are planned (see
> [Roadmap](../roadmap.md#next-steps), "Schema Translation Tooling"). This
> page will document each of them as it becomes available.

## From workflow languages to IO schemas

- **Nextflow:** from `nextflow_schema.json` (`nf-schema`); planned (see
  [issue #1](https://github.com/uniqueg/ga4gh-io-schema/issues/1)). It is
  to drop `fa_icon` (the profile has no icon keyword since version 0.3, see
  [Roadmap](../roadmap.md#cut)), to map a sample sheet's `schema` only to
  the experimental `x-ga4gh-tabular-schema` hint, and not to map
  `uniqueEntries` to `uniqueItems`, which means something else (see
  [Keywords](../specification/keywords.md#leveraging-native-json-schema-what-we-dont-reinvent)).
- **Snakemake:** from the config schema and the sample-sheet schemas; see
  [Snakemake converter](convert-snakemake.md).
- **CWL:** from the inputs and outputs of a `Workflow` or `CommandLineTool`;
  planned.
- **WDL:** from `input`, `output` and `parameter_meta` blocks; planned.

Converters emit only keywords and values of the profile version that they
target: output with removed ones (e.g., `x-ga4gh-fa-icon`, the `rst`
description format, the `password` widget) fails validation.

## From IO schemas to WES

- **WES `workflow_params`:** build the `workflow_params` of a WES run request
  from values that are valid against an IO schema; planned.
