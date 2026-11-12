# TRS

## Tool Registry Service (TRS) integration

To allow clients to discover these schemas natively, we recommend extending the TRS specification to formally recognize schemas as primary artifacts.

Specifically, TRS should introduce a new enum value for the `ToolFile` `file_type`, such as `IO_SCHEMA`. To ensure TRS remains agnostic and does not artificially lock out other ecosystem schemas, this file type should be accompanied by metadata or an annotation pointing to a standardized vocabulary of schema types (e.g., `ga4gh-io-schema`, `nf-schema`). This distinct file type allows generic clients (or AI agents) to pull the lightweight JSON contract independently from downloading the heavier, engine-specific source code.

## Guide for TRS implementers

> **To be written.** This section will describe, step by step, how a TRS
> implementation serves IO schemas for its tools and workflows, and how
> clients find them.
