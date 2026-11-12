# Converters

> **To be written.** Converters are planned (see
> [Roadmap](../roadmap.md#next-steps), "Schema Translation Tooling"). This
> page will document each of them as it becomes available.

## From workflow languages to IO schemas

- **Nextflow:** from `nextflow_schema.json` (`nf-schema`); planned (see
  [issue #1](https://github.com/uniqueg/ga4gh-io-schema/issues/1)).
- **Snakemake:** from JSON Schema and PEP configuration; planned.
- **CWL:** from the inputs and outputs of a `Workflow` or `CommandLineTool`;
  planned.
- **WDL:** from `input`, `output` and `parameter_meta` blocks; planned.

## From IO schemas to WES

- **WES `workflow_params`:** build the `workflow_params` of a WES run request
  from values that are valid against an IO schema; planned.
