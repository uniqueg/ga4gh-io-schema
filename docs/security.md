# Security considerations

## Security vs. client-side UX

It is important to explicitly distinguish between UX optimization and true system security. Complex client-side validation (enabled by this schema) is a "shift-left" operational strategy. It prevents users from submitting malformed data that will ultimately crash hours into a cloud run, saving significant time and compute costs.

However, client-side validation is *not* a security boundary. A malicious actor may still be able to bypass a UI and `POST` malformed data directly to a public API endpoint. True security (such as preventing shell injection in the execution layer or enforcing strict hardware memory limits) remains the sole responsibility of the API gateway and the underlying execution engine.

## Related sections

- [Tabular data and cloud sovereignty](specification/keywords.md#tabular-data-and-cloud-sovereignty):
  which validation belongs on the client and which behind the firewall.
- [Server-side validation in WES](adoption/wes.md): the "trust but verify"
  posture of WES implementations.
- [Non-goals](motivation.md#non-goals-and-out-of-scope-the-defenses): hardware
  limits are a server-side policy, not a schema validation task.

## Further considerations

> **To be written.** This section will cover further considerations for
> schemas, servers and clients, e.g., the handling of references to remote
> schemas and of file references.
