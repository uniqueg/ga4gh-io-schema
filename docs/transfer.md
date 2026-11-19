# Path to GA4GH

**Status: on hold, no date.** The next step is the feedback of the GA4GH
[Federated Analysis Work
Stream](https://www.ga4gh.org/work_stream/federated-analysis-work-stream-formerly-cloud-work-stream/)
on version 0.3.0, as a product candidate. Until that feedback, nothing on
this page is scheduled.

The goal of the profile is a GA4GH product. This page records where the
profile stands on the way there and proposals for its naming, approval and
identifiers. GA4GH decides on them, and none of them is agreed yet.

The profile has no tags or releases. The repository moved from
`uniqueg/ga4gh-io-schema` to `elixir-cloud-aai/ga4gh-io-schema`
([#25](https://github.com/elixir-cloud-aai/ga4gh-io-schema/issues/25)); a
move to the `ga4gh` organisation would follow GA4GH's acceptance. The
licences stay as they are (see
[Licences](governance.md#licences)).

## Naming

**Status.** The product name, the package metadata and the schema titles
name no organisation other than GA4GH:

| Item | Current name |
| ----- | ----- |
| Product | GA4GH IO Schema Profile |
| Python distribution, command | `ga4gh-io-schema` |
| Python import package | `ga4gh_io_schema` |
| Schema titles | `GA4GH IO Profile …` (e.g., "GA4GH IO Profile Meta-Schema"), and "GA4GH UI Widgets Vocabulary" |
| Repository | `elixir-cloud-aai/ga4gh-io-schema` (moved from `uniqueg/ga4gh-io-schema`) |

The copyright notices, `SPDX-PackageSupplier` in `REUSE.toml`, the
maintainer in the README and the URLs (the repository, the documentation's
`repo_url` and the `$id`s of the schemas, see [Identifiers](#identifiers))
name the current host. They change with a transfer, not before.

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
  standard rather than a host, and nothing is published on PyPI, so a
  different name requested by GA4GH costs little now.
- **Schema titles:** keep the `GA4GH IO Profile …` titles; rename "GA4GH UI
  Widgets Vocabulary" to "GA4GH IO Profile UI Widget Keywords" to match the
  others, with the first release. Titles aren't part of the profile's
  rules, so the rename isn't breaking.

## Approval

- **Work stream:** the Federated Analysis Work Stream (formerly the Cloud
  Work Stream), which maintains TRS and WES, the two APIs that the profile
  builds on.
- **First goal:** the work stream treats the profile as a product
  candidate. That needs neither product co-leads from other organisations
  nor a second implementation; both come later, for approval.
- **Approval path:** the [Product Development and Approval
  Process](https://www.ga4gh.org/our-products/development-and-approval-process/)
  has these stages: pre-planning (check against GA4GH policies, find the
  group the topic belongs to), study (a problem statement, reviewed by the
  Product Review Committee; the Product Steering Committee votes on
  development), development, approval (at least one month of public
  comment, reviews by the Regulatory & Ethics and Data Security work
  streams and the Product Review Committee, a ballot of the Product
  Steering Committee) and updates. The profile is at pre-planning: an
  incubator outside GA4GH, with a specification, conformance classes, a
  conformance suite and a prototype, whose outputs could feed a study group
  directly.
- **Implementations:** for approval, GA4GH expects at least two
  implementations by independent groups, at least one of them open, with
  interoperability demonstrated (for client-server products, two clients
  and two servers in different systems). Where the profile stands, by
  conformance class (see [Implementations](specification/conformance.md#implementations)):

  | Class | Implementations | Met? |
  | ----- | ----- | ----- |
  | Validator | `ga4gh-io-schema` (Python) | No: one |
  | Request builder (client) | `ga4gh-io-schema` (Python); ELIXIR Cloud Components (TypeScript, planned) | No: one, one planned |
  | Form renderer (client) | Form proof of concept in this repository; ELIXIR Cloud Components (planned) | No |
  | WES server | `ga4gh-io-schema wes-validate` (a library, not yet in a WES) | No: none in a WES |
  | Output normaliser | `ga4gh-io-schema` (Python); ELIXIR Cloud Components (planned) | No: one, one planned |

  All implementations so far come from one group.

## Identifiers

**Status.**

- **0.3.0:** the `$id`s name `elixir-cloud-aai/ga4gh-io-schema/main`, e.g.,
  `https://raw.githubusercontent.com/elixir-cloud-aai/ga4gh-io-schema/main/schemas/ga4gh-io-profile.schema.json`
  ([#78](https://github.com/elixir-cloud-aai/ga4gh-io-schema/pull/78)).

This form binds the identifier to a host organisation and a repository
name, so each transfer changes it, and its content changes over time. That
is acceptable while there are no releases. It must end with the first
release, which needs `$id`s that keep naming the same content (see
[Releases](governance.md#releases)).

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

For example, for a first release 0.4.0:

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

After a transfer, the target changes to `ga4gh/io-schema`, and no `$id`
changes:

```apache
RewriteRule ^schema/io-schema/([^/]+)/(.+)$ https://raw.githubusercontent.com/ga4gh/io-schema/$1/schemas/$2 [R=302,L]
```

The redirect is temporary (`302`), unlike the `301` of the GKS rules, so
that clients don't cache the target and it can change again, e.g., to a
GitHub Pages site with JSON media types.

**Steps.**

1. **Agree on the namespace:** the work stream leads and the administrators
   of `ids/ga4gh/` agree to the path `schema/io-schema/`. The namespace is
   GA4GH's, and the profile isn't a GA4GH product yet, so this can't be
   done without them.
2. **Submit the rule:** a pull request to `perma-id/w3id.org` adds the rule
   above, with GA4GH's agreement.
3. **Change the `$id`s:** the first release of the profile (the first one
   with tags) uses the w3id `$id`s and is tested through the redirect.
4. **Transfer:** after a transfer to `ga4gh`, a second pull request changes
   the rule's target. The `$id`s stay the same.

**Old URLs.** After a transfer, GitHub redirects the old repository URLs,
raw file URLs included, as long as no new repository takes the old name.
Validators shouldn't fetch the meta-schema at all: the `ga4gh-io-schema`
package bundles the schemas and resolves them by `$id`.
