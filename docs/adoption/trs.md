# TRS

## Tool Registry Service (TRS) integration

IO schemas are published as files of a workflow's TRS entry, with the existing `ToolFile` `file_type` `OTHER` and a naming convention (see [#12](https://github.com/uniqueg/ga4gh-io-schema/issues/12)), so that clients can fetch the lightweight JSON contract without downloading the engine-specific source code. This works with TRS as it is.

Earlier versions of this proposal asked TRS for a new file type, such as `IO_SCHEMA`, with metadata naming the schema standard of the file (e.g., `ga4gh-io-schema`, `nf-schema`). That change to TRS is deferred to a later proposal (see [Roadmap](../roadmap.md#deferred)).

## Guide for TRS implementers

> **To be written.** This section will describe, step by step, how a TRS
> implementation serves IO schemas for its tools and workflows, and how
> clients find them.
