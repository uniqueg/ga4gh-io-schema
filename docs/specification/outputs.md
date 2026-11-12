# Output contract

Outputs are traditionally the most opaque part of pipeline execution. The IO Profile solves this by establishing a **Key-Matching Contract** that separates semantic instructions from physical data retrieval.

## The key-matching mechanism

An AI agent or UI client does not need to know which internal `/scratch` folder an engine used, nor does it need to scan an output directory guessing which file is the alignment BAM. The contract works via a simple JSON key intersection:

1. **The Schema (The "What"):** The IO Profile defines the semantic intent of an output key.
   *(e.g., `"qc_report": { "x-ga4gh-ui-widget": "html-viewer" }`)*

2. **The Execution Log (The "Where"):** When the engine finishes (e.g., via a WES `RunLog`), the server responds with the physical location of that same key.
   *(e.g., `"outputs": { "qc_report": "s3://bucket/results/multiqc_report.html" }`)*

3. **The Client (The Merge):** The UI or Agent cross-references the keys. It now possesses the file's physical URL *and* the instruction to show it in a sandboxed HTML viewer (see [Rendering schemas and outputs](../security.md#rendering-schemas-and-outputs)). Outputs without a widget, or with one that the client doesn't know, are offered for download.

## Chaining workflows (deferred)

Because one workflow's output can be another workflow's input, the `x-ga4gh-ontology` terms on both sides of the contract hint which outputs may fit which inputs. Chaining workflows by these terms is deferred in version 0.3 (see [Roadmap](../roadmap.md#deferred)): a single exact term is not enough to decide that a file fits, as it doesn't cover more specific terms (subclasses), and it says nothing about, e.g., the genome build, the compression or the VCF version. The profile defines no matching rules; clients that suggest candidates do so on their own terms.

See also [the `x-ga4gh-*` vocabulary](keywords.md#the-x-ga4gh-vocabulary).
