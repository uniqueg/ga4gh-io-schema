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

Because one workflow's output can be another workflow's input, the `x-ga4gh-ontology` terms on both sides of the contract give an agent (or a person) a hint which outputs may fit which inputs. If Workflow A produces an output tagged with the EDAM term for VCF, and Workflow B has an input tagged with the same term, B is a *candidate* for A's output. A single exact term is not enough to decide that the file fits: it doesn't cover more specific terms (subclasses), and it says nothing about, e.g., the genome build, the compression or the VCF version. Rules for matching are not part of this version of the profile.

See also [the `x-ga4gh-*` vocabulary](keywords.md#the-x-ga4gh-vocabulary).
