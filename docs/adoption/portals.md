# Portals and clients

## Data Repository Service (DRS) interplay

The `x-ga4gh-drs-uri` flag acts as a critical bridge between the UI and the data access layer. By tagging an input string with this annotation, a WES client is proactively signaled to spawn a DRS resolution or authorization widget *before* submitting the compute request, guaranteeing that the WES runner receives actionable data locators rather than unresolved, potentially inaccessible identifiers.

See also [the `x-ga4gh-*` vocabulary](../specification/keywords.md#the-x-ga4gh-vocabulary)
and the [output contract](../specification/outputs.md).

## Guide for portals and clients

> **To be written.** This section will describe, step by step, how portals,
> other clients and AI agents render input forms from an IO schema, use the
> UI hints, and interpret the outputs of a run.
