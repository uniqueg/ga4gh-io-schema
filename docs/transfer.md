# Transfer to GA4GH

The goal of the profile is a GA4GH product. This page prepares the transfer
of the repository to the `ga4gh` organisation on GitHub: naming, licence,
governance and stable identifiers. It records proposals. GA4GH decides on
them during submission, and none of them is agreed yet.

Until the transfer, the profile has no tags or releases. The repository
moves from `uniqueg/ga4gh-io-schema` to
`elixir-cloud-aai/ga4gh-io-schema` first, and to the `ga4gh` organisation
when GA4GH accepts it.

## Naming

**Status.** The product name, the package metadata and the schema titles
name no organisation other than GA4GH:

| Item | Current name |
| ----- | ----- |
| Product | GA4GH IO Schema Profile |
| Python distribution, command | `ga4gh-io-schema` |
| Python import package | `ga4gh_io_schema` |
| Schema titles | `GA4GH IO Profile …` (e.g., "GA4GH IO Profile Meta-Schema"), and "GA4GH UI Widgets Vocabulary" |
| Repository | `uniqueg/ga4gh-io-schema`, moving to `elixir-cloud-aai/ga4gh-io-schema` |

Some names still point to the organisations where the profile was
developed:

- the copyright notices (`ELIXIR On-Cloud`, see [Licence](#licence));
- `SPDX-PackageSupplier` in `REUSE.toml` and the maintainer in the README;
- URLs: the repository, the documentation's `repo_url`, and the `$id`s of
  the schemas (see [Identifiers](#identifiers)).

These names belong to the current host. They change with the transfer, not
before.

**Proposal.**

- **Repository:** `ga4gh/io-schema`. GA4GH names product repositories after
  the product, without the `ga4gh-` prefix that the organisation already
  gives (e.g., `ga4gh/vrs`, `ga4gh/va-spec`, `ga4gh/refget`). API
  specifications use `*-schemas` (e.g., `ga4gh/workflow-execution-service-schemas`),
  but the profile isn't an API.
- **Product name:** "GA4GH IO Schema" once GA4GH approves it. Until then,
  the docs keep saying that it is a proposal and not a GA4GH standard (see
  [Versioning and governance](governance.md#status)). One question for the
  work stream is whether a product under study may keep "GA4GH" in its name
  and package name.
- **Package:** keep `ga4gh-io-schema` and `ga4gh_io_schema`. Both name the
  standard rather than a host, and nothing is published on PyPI yet, so a
  different name requested by GA4GH costs little now. One alternative is a
  `ga4gh` namespace package, `ga4gh.io_schema`, as in the VRS reference
  implementation (`ga4gh.vrs`).
- **Schema titles:** keep the `GA4GH IO Profile …` titles. Rename "GA4GH UI
  Widgets Vocabulary" to "GA4GH IO Profile UI Widget Keywords" to match the
  others, in the release that introduces the new `$id`s. Titles aren't part
  of the profile's rules, so the rename isn't breaking.

## Licence

**Status.** The repository uses REUSE (`REUSE.toml`, `reuse lint` in CI):

| Part | Licence |
| ----- | ----- |
| Code, schemas, tests, examples, prototype, README | Apache-2.0 |
| Documentation (`docs/`) | CC-BY-4.0 |
| Third-party test data (e.g., from nf-core and the CWL project) | Their own licences (e.g., MIT), as stated in their files |

**GA4GH practice.**

- **GA4GH Copyright Policy** ([ga4gh.org/copyright-policy](https://www.ga4gh.org/copyright-policy/)):
  - GA4GH licenses *Released Software* under the Apache License. It may
    choose another open source licence for particular items, e.g., test
    suites (section 6).
  - *Released Documents* come under GA4GH's own licence to copy, distribute
    and adapt them (section 5a). Every reproduction must carry "Created by
    GA4GH", the existing copyright notices, and the sentence "Use and
    reproduction of this document is subject to the terms of the GA4GH
    Copyright Policy" (section 5b).
  - Contributors grant GA4GH a perpetual, irrevocable, non-exclusive,
    sub-licensable licence to their contributions and keep their copyright
    (section 3a). GA4GH owns the copyright in the work product (section 7).
- **GA4GH repositories:** the specification repositories checked on
  2026-11-17 declare Apache-2.0 for the whole repository, documentation
  included:
  - `ga4gh/workflow-execution-service-schemas`
  - `ga4gh/tool-registry-service-schemas`
  - `ga4gh/data-repository-service-schemas`
  - `ga4gh/task-execution-schemas`
  - `ga4gh/vrs`
  - `ga4gh/va-spec`
  - `ga4gh-discovery/ga4gh-service-info`

**Assessment.**

- **Code and schemas:** Apache-2.0 matches GA4GH practice. Nothing changes.
- **Documentation:** CC-BY-4.0 lets GA4GH copy, adapt and redistribute the
  docs, so it doesn't block the transfer. It differs from the GA4GH
  repositories, though, and the Copyright Policy puts released documents
  under GA4GH's own terms. Proposal: on transfer, the docs follow GA4GH's
  choice, which is Apache-2.0 like the rest of the repository if GA4GH
  agrees, and get the notice of section 5b. Until then, they stay
  CC-BY-4.0. Changing the licence needs the consent of everyone who holds
  copyright in the docs. Today that is the one human author of the
  repository.
- **Third-party files:** they keep their licences. Section 6 of the policy
  allows other open source licences for test material.

**Copyright notices** are inconsistent today. 48 files say
`ELIXIR On-Cloud <cloud-service@elixir-europe.org>`, while `REUSE.toml` and
11 files say `ELIXIR On-Cloud / GA4GH Contributors`. Neither form names a
legal person
that holds the copyright. Proposal:

1. **Before the transfer:** a single notice, "The GA4GH IO Schema
   contributors", in all headers and in `REUSE.toml`. Copyright then stays
   with the individual contributors, as section 3a of the policy assumes.
   This is one mechanical change, best made when no other pull requests are
   open, and the holder named in it is the maintainer's decision.
2. **On transfer:** the notices that GA4GH asks for (section 7 and its
   repository template).

## Governance

- **Work stream:** the [Federated Analysis Work
  Stream](https://www.ga4gh.org/work_stream/federated-analysis-work-stream-formerly-cloud-work-stream/)
  (formerly the Cloud Work Stream), which maintains TRS and WES, the two
  APIs that the profile builds on.
- **Product leads:** the product needs leads who make decisions by
  consensus and make sure decisions are communicated. Proposal: the current
  maintainer, Alexander Kanitz, plus at least one co-lead from another
  organisation, ideally one that implements TRS or WES. The co-lead is not
  named yet.
- **Approval path:** the [Product Development and Approval
  Process](https://www.ga4gh.org/our-products/development-and-approval-process/)
  has these stages:
  1. **Pre-planning:** check against GA4GH policies and find the group the
     topic belongs to; the work stream leads decide by consensus.
  2. **Study:** a study group writes a problem statement. The Product Review
     Committee reviews it, and the Product Steering Committee votes on
     whether to move to development.
  3. **Development**.
  4. **Approval:** at least one month of public comment, then review by the
     Regulatory & Ethics and Data Security work streams and the Product
     Review Committee, and a ballot of the Product Steering Committee.
  5. **Updates:** patch, minor and major releases.

  The profile is at pre-planning. It is an incubator outside GA4GH, with a
  specification, conformance classes, a conformance suite and a prototype,
  so its outputs could feed a study group directly.
- **Two implementations:** for approval, GA4GH expects at least two
  implementations by independent groups, at least one of them open, with
  interoperability demonstrated. Client-server products need two client
  and two server implementations in different systems. Status, by
  conformance class (see [Implementations](specification/conformance.md#implementations)):

  | Class | Implementations | Met? |
  | ----- | ----- | ----- |
  | Validator | `ga4gh-io-schema` (Python) | No: one |
  | Request builder (client) | `ga4gh-io-schema` (Python); ELIXIR Cloud Components (TypeScript, planned) | No: one, one planned |
  | Form renderer (client) | Form proof of concept in this repository; ELIXIR Cloud Components (planned) | No |
  | WES server | `ga4gh-io-schema wes-validate` (a library, not yet in a WES) | No: none in a WES |
  | Output normaliser | `ga4gh-io-schema` (Python); ELIXIR Cloud Components (planned) | No: one, one planned |

  The implementations so far all come from one group, so the requirement
  isn't met. To meet it, the work needs a second, independent group,
  validation in at least two WES servers, and a demonstration with two
  clients against two servers (e.g., at a GA4GH Connect or Implementation
  Forum session).

## Identifiers

**Status.**

- **0.3 (no tag, [#78](https://github.com/uniqueg/ga4gh-io-schema/pull/78)):**
  the `$id`s and `$schema` of the profile name the `main` branch of the
  repository's new home
  ([#25](https://github.com/uniqueg/ga4gh-io-schema/issues/25)), e.g.,
  `https://raw.githubusercontent.com/elixir-cloud-aai/ga4gh-io-schema/main/schemas/ga4gh-io-profile.schema.json`.

Drafts of 0.3 named the repository under `uniqueg` and a `v0.3.0` tag,
which was never created. Both forms bind the identifier to a host
organisation and a repository name, so each transfer changes them. The
`main` form also changes its content over time. That is acceptable while there are no releases. It must
end with the first release, which needs `$id`s that keep naming the same
content (see [Releases](governance.md#releases)).

**Proposal: a w3id.org redirect in the GA4GH namespace.**

[w3id.org](https://w3id.org) provides permanent URLs that redirect to the
current location. GA4GH already holds the namespace
`https://w3id.org/ga4gh/`, administered by GA4GH staff
([`ids/ga4gh/`](https://github.com/perma-id/w3id.org/tree/master/ids/ga4gh)
in `perma-id/w3id.org`). It already redirects the schema `$id`s of the
Genomic Knowledge Standards (e.g., `https://w3id.org/ga4gh/schema/vrs/…`) to
their GitHub repositories. Following that pattern, the profile's `$id`s
would become:

```text
https://w3id.org/ga4gh/schema/io-schema/{ref}/{path under schemas/}
```

For example:

```text
https://w3id.org/ga4gh/schema/io-schema/v0.4.0/ga4gh-io-profile.schema.json
https://w3id.org/ga4gh/schema/io-schema/v0.4.0/vocabularies/file.schema.json
```

`{ref}` is a tag of a release, or `main` for the schemas under development.
The `$id`s of embedded resources follow the same pattern, e.g.,
`…/v0.4.0/ga4gh-io-profile-node`.

The rule for `ids/ga4gh/.htaccess`, added next to the GKS rules, points to
the current home of the repository:

```apache
# IO Schema (Federated Analysis Work Stream), schema $ids
RewriteRule ^schema/io-schema/([^/]+)/(.+)$ https://raw.githubusercontent.com/elixir-cloud-aai/ga4gh-io-schema/$1/schemas/$2 [R=302,L]
```

After the transfer, the target changes to `ga4gh/io-schema`, and no
`$id` changes:

```apache
RewriteRule ^schema/io-schema/([^/]+)/(.+)$ https://raw.githubusercontent.com/ga4gh/io-schema/$1/schemas/$2 [R=302,L]
```

The redirect is temporary (`302`), unlike the `301` of the GKS rules. Then
clients don't cache the target, and it can change again, e.g., to a GitHub
Pages site with JSON media types.

**Steps.**

1. **Agree on the namespace:** the work stream leads and the administrators
   of `ids/ga4gh/` agree to the path `schema/io-schema/`. The namespace is
   GA4GH's, and the profile isn't a GA4GH product yet, so this can't be
   done without them.
2. **Submit the rule:** a pull request to `perma-id/w3id.org` adds the rule
   above, with GA4GH's agreement.
3. **Change the `$id`s:** the next release of the profile (the first one
   with tags) uses the w3id `$id`s and is tested through the redirect.
4. **Transfer:** after the transfer to `ga4gh`, a second pull request
   changes the rule's target. The `$id`s stay the same.

**Old URLs keep resolving.**

- After a transfer, GitHub redirects the old repository URLs as long as no
  new repository takes the old name. Raw file URLs are part of this, but
  this needs testing when the repository moves to `elixir-cloud-aai`
  (#25).
- Validators shouldn't fetch the meta-schema at all: the
  `ga4gh-io-schema` package bundles the schemas and resolves them by
  `$id`. Proposal: the package keeps the `$id`s of 0.3 (`uniqueg/…/v0.3.0`)
  and of `main` (`elixir-cloud-aai/…/main`) as aliases in its registry, so
  documents that name them keep validating offline.
