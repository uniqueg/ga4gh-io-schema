# Output contract

Outputs are traditionally the most opaque part of pipeline execution. The IO Profile solves this by establishing a **Key-Matching Contract** that separates semantic instructions from physical data retrieval.

## The key-matching mechanism

An AI agent or UI client does not need to know which internal `/scratch` folder an engine used, nor does it need to scan an output directory guessing which file is the alignment BAM. The contract works via a simple JSON key intersection:

1. **The Schema (The "What"):** The IO Profile defines the semantic intent of an output key.
   *(e.g., `"alignment_track": { "x-ga4gh-ui-widget": "genome-browser" }`)*

2. **The Execution Log (The "Where"):** When the engine finishes (e.g., via a WES `RunLog`), the server responds with the physical location of that same key.
   *(e.g., `"outputs": { "alignment_track": "s3://bucket/results/sample.bam" }`)*

3. **The Client (The Merge):** The UI or Agent cross-references the keys. It now possesses the file's physical URL *and* the instruction to load it directly into an interactive genome browser component.

## Agentic chaining

This explicit input and output contract is what makes the ecosystem truly "Agent-Ready." Because one workload's output is another workload's input, an AI tasked with chaining workflows together relies on the `x-ga4gh-ontology` terms mapped across both sides of the contract. If Workflow A produces an output tagged as an EDAM VCF format, the agent deterministically knows it can route that URL directly into Workflow B's input that demands a VCF format, without ever downloading or inspecting the file.

See also [the `x-ga4gh-*` vocabulary](keywords.md#the-x-ga4gh-vocabulary).
