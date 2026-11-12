# Roadmap

## Next steps

To drive adoption and prove out the utility of the IO Schema Profile, we propose the following immediate next steps:

1. **Schema Translation Tooling:** Develop lightweight, open-source translation scripts to convert existing `nextflow_schema.json` and CWL `CommandLineTool` inputs into compliant GA4GH IO Profile schemas.

2. **AI Agent Reference Implementations:** Publish a reference implementation of an LLM agent instructed to "auto-draft" compliant IO Schemas.

3. **End-to-End Proof of Concept (PoC):** Construct a sandbox environment featuring a mock TRS registry hosting `.schema.json` files, a generic frontend (e.g., via `react-jsonschema-form`) rendering input forms and compiling WES requests, and a proxy WES gateway enforcing server-side validation against the schema prior to execution.

4. **Formal Specification Submission:** Following the PoC, submit the IDL schema structure, the `x-ga4gh-*` vocabulary, and the proposed API modifications to the GA4GH Federated Analysis Work Stream for formal standardization review.

## Document history

| Version | Date | Author | Notes |
| ----- | ----- | ----- | ----- |
| **v0.1** | 2026-10-10 | Alexander Kanitz | Initial Draft: Ecosystem survey, evaluation, and GA4GH JSON Schema Profile proposal. |
| **v0.2** | 2026-10-13 | Alexander Kanitz | Major rewrite addressing architectural reviews. Reframed standard as a universal Interface Definition Language (IDL). Explicitly scoped out bare TES execution. Clarified tabular data sovereignty. Mapped custom properties to `nf-schema`. Expanded GA4GH API lifecycle and RO-Crate Profiles integration. |
