# Conformance

> **To be written.** This page will define what it means to conform to the
> GA4GH IO Schema Profile, with requirement levels (MUST, SHOULD, MAY) for:
>
> - IO schemas (documents validated against the [meta-schema](meta-schema.md));
> - servers that validate requests against IO schemas (e.g.,
>   [WES](../adoption/wes.md) implementations);
> - clients that render forms from or build requests with IO schemas (see
>   [Portals and clients](../adoption/portals.md)).
>
> Until then, the requirements are those stated in [Keywords](keywords.md),
> [Output contract](outputs.md) and the [adoption guides](../adoption/index.md).

## Security requirements

The requirements of [Security considerations](../security.md) are part of
conformance:

- **IO schemas** MUST meet the requirements for schemas there (e.g., no
  inputs for secrets; bundled references).
- **Servers** MUST meet the requirements for servers (sources of schemas,
  regular expressions and size limits, URI schemes, access to data, error
  messages and logs, validation of data files).
- **Clients** MUST meet the requirements for clients, in particular the
  [rendering rules](../security.md#rendering-schemas-and-outputs), the URI
  scheme allow-list and the rules for [access to
  data](../security.md#access-to-data).
