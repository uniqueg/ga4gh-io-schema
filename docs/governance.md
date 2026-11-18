# Versioning and governance

## Status

The GA4GH IO Schema Profile is an incubator: a proposal developed in the
open, outside the formal process of GA4GH. It is not an approved GA4GH
standard. The goal is to submit it to the GA4GH
[Federated Analysis Work Stream](https://www.ga4gh.org/work_stream/federated-analysis-work-stream-formerly-cloud-work-stream/)
(see [Roadmap](roadmap.md)); from then on, the work stream's process
applies, and this page will be replaced by it. GA4GH approval also needs at
least two independent, interoperating implementations (see
[Implementations](specification/conformance.md#implementations)).
[Path to GA4GH](transfer.md) says where the profile stands on the way to
a GA4GH product, with proposals for its naming, approval and identifiers.

## Versions of the profile

The profile has semantic versions, `MAJOR.MINOR.PATCH`
([Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html)). A
version covers the normative text (see
[Conformance](specification/conformance.md#notational-conventions)), the
meta-schema and vocabularies in `schemas/`, and the
[conformance suite](specification/conformance.md#conformance-suite).

!!! note "Until the first release"
    There are no releases yet (see [Releases](#releases)). Until the first
    one, the `$id` of the meta-schema names the `main` branch, so `$schema`
    doesn't tell versions apart, and breaking changes on `main` keep it as
    it is. Pin a commit to fix the version that you use (see [Schema
    identifiers](development.md#schema-identifiers)). The rules below apply
    from the first release on.

Each release has a meta-schema of its own, with the release in its `$id`,
and a schema document names the release that it targets in `$schema`. To
move a document to a new release, its author changes `$schema` (a
[validator](specification/conformance.md#validator) checks a document
only against the versions that it supports). Whether a change is breaking
is judged on documents moved this way: a change is **breaking** if, after
it, a document or implementation that conformed to a class no longer
does, or reads a conforming document differently. For example:

- removing or renaming a keyword, a value of a vocabulary (e.g., a UI
  widget) or a conformance class;
- a new rule of the meta-schema that rejects schema documents that it
  accepted before (a valid case of the conformance suite that fails);
- a new requirement (MUST or MUST NOT) for an existing class, or a SHOULD
  that becomes a MUST;
- a change of the meaning of a keyword or of the outputs model.

Other changes are **non-breaking**: new optional keywords, vocabulary values
or conformance classes; requirements that become weaker; clarifications and
corrections of the text that don't change what conforms; new cases of the
conformance suite for existing rules.

- **MAJOR** versions contain breaking changes; **MINOR** versions add
  features without breaking changes; **PATCH** versions only correct the
  text, the meta-schema or the suite, so that they say what the version
  already meant.
- Before version 1.0.0, MINOR versions may contain breaking changes, as
  semantic versioning allows. The [changelog](changelog.md) lists them under
  "Breaking changes", with what to change.
- Each schema document names the version that it targets: `$schema` is the
  `$id` of that version's meta-schema (see
  [Referencing the meta-schema](specification/meta-schema.md#referencing-the-meta-schema)).
  A new version of the profile doesn't change what an existing schema
  document means; for a non-breaking version, changing `$schema` is all
  that moving a document to it takes.

## Releases

- There are no releases yet: versions 0.1 to 0.3 have no tags (see
  [Changelog](changelog.md)). Releases, as Git tags `vMAJOR.MINOR.PATCH`,
  come with the move of the repository to GA4GH.
- Until then, the `$id`s of the meta-schema and vocabularies name the
  `main` branch of the repository, which holds the latest reviewed state
  (they resolve once version 0.3 is merged into `main` at
  elixir-cloud-aai). To use fixed content, pin a commit SHA (see [Schema
  identifiers](development.md#schema-identifiers)). A stable identifier for
  released versions follows with the first release.
- The Python package `ga4gh-io-schema` isn't published on PyPI; install it
  from the repository, at a commit (see
  [Installation](tools/validator.md#installation)).

## Licences

The repository follows the [REUSE specification](https://reuse.software/):
each file names its licence and copyright, in an SPDX header or in
`REUSE.toml`, and `reuse lint` checks them in CI. The full licence texts are
in `LICENSES/`.

| Part | Licence |
| ----- | ----- |
| Code, schemas, tests, examples, prototype, README | Apache-2.0 |
| Documentation (`docs/`) | CC-BY-4.0 |
| Third-party test data (e.g., from nf-core and the CWL project) | Their own licences (e.g., MIT), as stated in their files |

These licences stay as they are, also on the way to GA4GH: Apache-2.0 for
the code and schemas, CC-BY-4.0 for the documentation. GA4GH's new
repository template requires REUSE, so that the licence of each file is
clear; older GA4GH repositories, which declare one licence for the whole
repository, haven't caught up yet. Third-party files keep their licences.

The copyright notices name ELIXIR On-Cloud, as in the other repositories of
elixir-cloud-aai; files that still use another form are aligned separately
([#99](https://github.com/elixir-cloud-aai/ga4gh-io-schema/issues/99)).

## Proposing changes

- Propose a change, or report a problem, as an issue in the
  [repository](https://github.com/elixir-cloud-aai/ga4gh-io-schema/issues): describe
  the problem and, where you can, the use case behind it.
- Changes are made by pull request. A pull request that changes the
  normative text changes the meta-schema, the conformance suite (a negative
  case for each new rule) and the changelog with it, and says whether the
  change is breaking.
- The maintainers of the repository review the pull requests and decide.
  Breaking changes are announced in the issue before they are merged, so
  that implementers can comment.
- To add an implementation to the
  [table of implementations](specification/conformance.md#implementations),
  open a pull request with its name, language, classes and status.
