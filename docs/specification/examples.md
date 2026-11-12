# Examples

The following examples demonstrate the schema in practice, utilizing the GA4GH IO Profile Meta-Schema to ensure compliance.

## Example 1: full workflow with tabular validation

This example demonstrates how to validate a workflow that takes a CSV sample sheet as input.

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

## Example 3: workflow bound to an engine

All examples carry `x-ga4gh-workflow`, which ties them to a version of a
workflow in a TRS and to its engine (see [Identity and engine
binding](identity.md)): Example 1 is a Nextflow workflow, Example 2 a CWL
tool in a document of its own, which needs no entry point. This WDL workflow also shows the entry point, which WDL requires, and
`x-ga4gh-parameter` with the WDL types of the parameters and, where they
differ from the property names, their WDL names.

The full schema is available at
[`tests/data/example_wdl.schema.json`](https://github.com/uniqueg/ga4gh-io-schema/blob/main/tests/data/example_wdl.schema.json):

```json
--8<-- "tests/data/example_wdl.schema.json"
```
