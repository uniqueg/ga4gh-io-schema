# Prototype evaluation

What the [prototype](prototype.md) showed about the profile: the flow from a
workflow in a tool registry to a WES run request, with a TRS stub and a
generic form host on one laptop (`prototype/`, version 0.3.0). The prototype
is a proof of concept; its conclusions are evidence for the proposal, not
results of a production deployment.

## Summary

- **The schema was enough.** The host found, checked and rendered the IO
  schema of a workflow it had never seen, and built a complete WES run
  request, with no code for the workflow and none for its language beyond
  the generic engine binding of the package.
- **TRS needed no change.** The [publishing
  convention](trs.md#publishing-convention) (a file of type `OTHER` named
  `ga4gh-io.schema.json` next to the primary descriptor) worked with the
  plain TRS v2 API, but clients must match file entries carefully.
- **The weak points are at the edges of the profile:** whether a WES can
  fetch the `workflow_url`, how a WES resolves the imports of a workflow
  that is more than one file, and checking the descriptor's checksum, which
  the reference tools leave to each client.

## What the flow relied on

| Step | Rules of the profile | Where |
| --- | --- | --- |
| Find the schema | The publishing convention: type `OTHER`, path `ga4gh-io.schema.json`, in the directory of the `PRIMARY_DESCRIPTOR`. | [Discovery by clients](trs.md#discovery-by-clients) |
| Trust the schema | Validation against the meta-schema; `x-ga4gh-workflow` names `trs_tool_id`, `trs_version_id` and `descriptor_type`, compared with what was fetched. | [The workflow block](../specification/identity.md#the-workflow-block), step 2 of the [guide](portals.md#2-check-the-workflow-block) |
| Render the form | JSON Schema with `title`, `description`, `default`, bounds and `enum`; `x-ga4gh-ui-widget` (`slider`, `radio`); file references with allowed schemes. | [UI widgets](../specification/widgets.md), [File references](../specification/files.md) |
| Report wrong values | Validation of the values; `x-ga4gh-error-message` of the failing location. | [Keywords](../specification/keywords.md), step 7 of the [guide](portals.md#7-validate-the-values) |
| Build the request | `x-ga4gh-parameter` names, qualified for WDL; `workflow_type` and `workflow_type_version` from the workflow block; the TRS URL of the plain primary descriptor as `workflow_url`. | [Engine bindings](../specification/engine-bindings.md#run-requests) |

## What worked without workflow-specific code

- **Picking:** the list of workflows is `GET /tools` of any TRS; a tool
  version without an IO schema gets an error, not a broken form.
- **The form:** labels, help texts, the required mark, the slider with its
  bounds, the radio buttons and the defaults all come from the schema. The
  page is the same for every workflow.
- **Errors:** the message for a mapping quality of 61 is the author's, from
  `x-ga4gh-error-message`; the portal has no text of its own for it.
- **The run request:** `workflow_params` in the shape of the WDL engine
  (`io_schema_demo.min_mapq`), `workflow_type` `WDL`, `workflow_type_version`
  `1.1` and the `workflow_url` are all derived; the user picks no language,
  version or engine parameter.
- **Tests:** the same path runs in CI, over the host's API and in a
  browser, against a stack built from the repository alone.

## Where the spec or the tools fell short

Each gap has an issue in this repository; the fixed ones link to the
pull request that closed them.

1. **Matching TRS file entries (docs).** The first version of the host
   compared whole file entries and missed the schema as soon as an entry
   had a `checksum`. TRS `ToolFile` fields are all optional, and paths may
   have forms such as `./ga4gh-io.schema.json`. Addressed
   ([#82](https://github.com/elixir-cloud-aai/ga4gh-io-schema/issues/82)):
   [Matching file entries](trs.md#matching-file-entries) says to compare
   entries by `file_type` and normalised `path` only, ignoring other
   fields, with test vectors; and this is the evidence for the [proposed
   `IO_SCHEMA` file type](trs.md#proposed-the-io_schema-file-type), which
   clients now look for first.
2. **Imports of multi-file workflows (spec).** The `workflow_url` that the
   binding recommended, `.../PLAIN_{type}/descriptor`, has no file name, so a
   relative import such as `tasks/sub.wdl` resolves to
   `.../PLAIN_{type}/tasks/sub.wdl`, which TRS doesn't serve;
   `.../PLAIN_{type}/descriptor/{primary path}` would resolve it to
   `.../descriptor/tasks/sub.wdl`. The demo is one file, so the prototype
   didn't hit this; it follows from URL resolution (RFC 3986). Decided in
   0.3.0: the form with the path is recommended ([Workflow URLs in
   TRS](../specification/engine-bindings.md#workflow-urls-in-trs));
   [#83](https://github.com/elixir-cloud-aai/ga4gh-io-schema/issues/83), fixed by [#89](https://github.com/elixir-cloud-aai/ga4gh-io-schema/pull/89).
3. **Can the WES fetch the `workflow_url`? (docs).** The run request is
   only useful if the WES can fetch the TRS URL. In the prototype, the stub
   is reachable inside the stack only, so the stack sends nothing by
   default; Conquest, in the [end-to-end demo](demo.md), takes no TRS URLs
   at all. A client can't find out from the WES API whether it resolves
   TRS URLs or which hosts it reaches. The [WES guide](wes.md) should say
   so, and the question belongs to the WES work stream. Done in 0.3.0: [Can
   the WES fetch the workflow?](wes.md#can-the-wes-fetch-the-workflow) and
   an [open question](../roadmap.md#open-questions);
   [#84](https://github.com/elixir-cloud-aai/ga4gh-io-schema/issues/84), fixed by [#87](https://github.com/elixir-cloud-aai/ga4gh-io-schema/pull/87).
4. **The workflow block check (tools).** The host compares the ids of
   `x-ga4gh-workflow` by hand and skips the checksum (step 2 of the
   [guide](portals.md#2-check-the-workflow-block)). The package validates
   schemas and builds requests, but has no function for this check; every
   client writes its own, and the checksum part is the one that gets left
   out. A helper that takes the schema, the TRS ids and the descriptor's
   `FileWrapper` would close it. Done in 0.3.0: the [workflow block
   check](../tools/verify.md), which the host uses;
   [#85](https://github.com/elixir-cloud-aai/ga4gh-io-schema/issues/85), fixed by [#92](https://github.com/elixir-cloud-aai/ga4gh-io-schema/pull/92).

## Limits of the prototype

- **No outputs:** it stops at the run request. The output side of the
  profile is shown by the [end-to-end demo](demo.md) and the [output
  normaliser](../tools/outputs.md), not here.
- **One workflow, one language:** WDL only, one file; CWL, Nextflow and
  Snakemake bindings are tested in the package, not in the stack.
- **No real services:** a TRS stub instead of a registry, no WES by
  default, no authentication, no DRS. Pointing it at a real TRS or WES
  (`TRS_URL`, `WES_URL`) was not part of the CI runs.
- **One form implementation:** the form of this repository; other form
  libraries (see [Form libraries](portals.md#form-libraries)) weren't
  tried.

## Lessons for implementers

- **Portals and clients:** match TRS file entries by type and path, not by
  equality; check `x-ga4gh-workflow` against the tool version before
  rendering; build the `workflow_url` for the WES that will run it, not for
  the portal's own network; treat a missing schema as a normal case.
- **TRS implementers:** serve the schema as an `IO_SCHEMA` file, or an
  `OTHER` file next to the primary descriptor, with a checksum, and serve the `PLAIN_` endpoints,
  which a WES can fetch without unwrapping a `FileWrapper`.
- **WES implementers:** accepting TRS URLs as `workflow_url` (including
  the imports next to the primary descriptor) is what makes the request
  that a generic client builds runnable as it is; engine-specific
  parameters, as Conquest needs them, break that.
