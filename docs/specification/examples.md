# Examples

The following examples demonstrate the schema in practice, utilizing the GA4GH IO Profile Meta-Schema to ensure compliance.

## Example 1: full workflow with a sample sheet

This example describes a workflow that takes a CSV sample sheet as input, with the experimental `x-ga4gh-tabular-schema` hint for its rows (see [Tabular data and cloud sovereignty](keywords.md#tabular-data-and-cloud-sovereignty)).

The full schema defining the workflow inputs and outputs is available at
[`tests/data/example_workflow.schema.json`](https://github.com/uniqueg/ga4gh-io-schema/blob/main/tests/data/example_workflow.schema.json):

```json
--8<-- "tests/data/example_workflow.schema.json"
```

## Example 2: single-step workflow component

This standard works equally well for defining modular, single-step units (such as a CWL `CommandLineTool` or an `nf-core` module) executed via a workflow orchestrator.

The full schema defining the modular component is available at
[`tests/data/example_tool.schema.json`](https://github.com/uniqueg/ga4gh-io-schema/blob/main/tests/data/example_tool.schema.json):

```json
--8<-- "tests/data/example_tool.schema.json"
```
