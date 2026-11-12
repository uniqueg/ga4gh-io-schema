# Security considerations

This page states what schemas, servers and clients that use the profile must do to handle schemas, requests, data and outputs safely. The key words "MUST", "MUST NOT", "SHOULD", "SHOULD NOT" and "MAY" are to be interpreted as described in [BCP 14](https://www.rfc-editor.org/info/bcp14) ([RFC 2119](https://www.rfc-editor.org/rfc/rfc2119), [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)) when, and only when, they appear in all capitals.

Roles, as used on this page:

- **Server:** a WES implementation or gateway that validates run requests against IO schemas.
- **Client:** a portal, other user interface, or AI agent that renders forms from IO schemas, builds run requests, or shows the outputs of runs.
- **Execution side:** the server and the workflow engine it runs, including the components that stage data for a run.

The requirements on this page are part of the [conformance](specification/conformance.md) requirements for servers and clients.

## Validation is not a security boundary

It is important to explicitly distinguish between UX optimization and true system security. Complex client-side validation (enabled by this schema) is a "shift-left" operational strategy. It prevents users from submitting malformed data that will ultimately crash hours into a cloud run, saving significant time and compute costs.

However, client-side validation is *not* a security boundary. A client can be bypassed, and anyone with access to the API can `POST` any request directly. Servers MUST NOT rely on validation by the client. Validation against an IO schema checks the shape of a request; it doesn't replace the checks of the execution side (e.g., against shell injection in the engine, or limits on resources), which remain the responsibility of the server and the workflow engine.

## Sources of schemas

A schema decides what a server accepts and which addresses a validator may look up, so it must come from a source that the deployment trusts.

- Servers MUST use only IO schemas from trusted sources: the TRS entry of the workflow (see [TRS](adoption/trs.md)) in a registry that the deployment trusts, or a schema bundled with the deployment.
- Servers MUST NOT accept IO schemas supplied by clients in a run request. Version 0.3 removes schemas "provided dynamically" from the profile.
- Servers MUST NOT resolve references to remote schemas (`$ref` or `$dynamicRef` to another host) while validating. Remote references would make the server send requests to addresses chosen by the schema's author, including internal addresses such as `169.254.169.254` (the metadata service of many cloud providers) or services behind the firewall; a valid URI is not a safe address.
- IO schemas SHOULD be bundled: all references are local (`#/$defs/…`) or point to the profile's meta-schema and vocabularies. Validators MUST load the meta-schema and vocabularies from local copies (as the [validator](tools/validator.md) does), not from the network.

## Regular expressions and size limits

The `pattern` and `patternProperties` keywords run regular expressions from the schema on values from the request. Some expressions take time that grows exponentially with the length of the input when matched by a backtracking engine.

- Schemas SHOULD use only the subset of the ECMA-262 dialect that JSON Schema recommends ([JSON Schema Core, §6.4](https://json-schema.org/draft/2020-12/json-schema-core#section-6.4)) and SHOULD avoid nested quantifiers (e.g., `(a+)+`).
- Servers MUST either match regular expressions with an engine that runs in linear time (e.g., [RE2](https://github.com/google/re2)) or limit the time spent on validation of a request.
- Servers SHOULD reject schemas with patterns longer than a limit set by the deployment (e.g., 1,000 characters).
- Servers MUST limit the size of the `workflow_params` they validate (e.g., 1 MiB) and SHOULD limit the depth of nested values; requests above the limits are rejected before validation.

## URIs and file references

The `uri` format of JSON Schema accepts any scheme of [RFC 3986](https://www.rfc-editor.org/rfc/rfc3986), including `javascript:`, `data:` and `file:`. Validation against `format: uri` therefore doesn't make a reference safe to use, and many validators don't check formats at all.

- Servers and clients MUST check the scheme of every file reference, in inputs and in outputs, against an allow-list before they use it: before staging an input, and before showing an output as a link or loading it into a viewer.
- The allow-list SHOULD contain only `drs` and `https`, plus the object-store schemes (e.g., `s3`, `gs`) and, for internal networks, `http`, that the deployment supports.
- `javascript`, `data`, `file` and other schemes that run code in a browser or read from the local file system of the server MUST NOT be on the allow-list. Servers MUST NOT accept relative paths as file references in inputs, and SHOULD return file references in outputs as absolute URIs.

The file reference type (see [#10](https://github.com/uniqueg/ga4gh-io-schema/issues/10)) will make the allowed schemes part of the profile.

## Rendering schemas and outputs

Text in an IO schema comes from the author of the workflow, and outputs come from the run, which may have processed files supplied by users. Clients MUST treat both as untrusted.

- **Text:** Clients MUST show `title`, `description`, enumeration values and `x-ga4gh-error-message` as text. If `x-ga4gh-description-format` is `markdown`, clients MUST render the Markdown with a sanitiser that removes raw HTML, scripts and event handlers, and that allows only links with schemes on the allow-list. Clients MUST NOT render descriptions as HTML.
- **Links:** Clients MUST check every link, in descriptions and outputs, against the allow-list of schemes before showing it.
- **HTML outputs (`html-viewer`):** Clients MUST show HTML outputs only in a sandboxed `iframe` (the `sandbox` attribute without `allow-scripts` and without `allow-same-origin`), served from an origin other than the client's own, or offer them for download only. HTML outputs are often built from files supplied by users (e.g., labels from a sample sheet), so a report from a trusted workflow can still contain markup from users.
- **Other viewers:** Clients MUST escape the cells of tables (`table-viewer`) and sanitise Markdown outputs (`markdown-viewer`) as for descriptions. Files that a client can't show safely are offered for download only (with `Content-Disposition: attachment`).

Viewers beyond download, table and sandboxed HTML are deferred in version 0.3 (see [#17](https://github.com/uniqueg/ga4gh-io-schema/issues/17)).

## Access to data

Clients identify input data; the execution side fetches it.

- Clients SHOULD submit inputs held in a Data Repository Service (DRS) as `drs://` identifiers in `workflow_params`, not as resolved access URLs.
- Clients MUST NOT put signed URLs, access tokens or other credentials in `workflow_params`. WES returns the request, including `workflow_params`, in the run log (`RunLog.request`); parameters also end up in the logs of the engine and in provenance records such as RO-Crates; and signed URLs can expire while the run waits in the queue.
- The execution side resolves the identifiers when it stages the data, with credentials delegated by the user (e.g., a token exchanged for the run, or GA4GH Passports), and only after it has checked the request.

This replaces the flow of earlier versions, in which the client resolved DRS identifiers and passed the resulting URLs to WES. See also [Portals and clients](adoption/portals.md#data-repository-service-drs-interplay).

## Secrets

- Workflow parameters are not a channel for secrets: schemas MUST NOT define inputs for passwords, API keys, tokens or other credentials. Version 0.3 removes the `password` widget (see [#17](https://github.com/uniqueg/ga4gh-io-schema/issues/17)).
- Credentials that a workflow needs are provided by the deployment (e.g., a secret store of the execution side, or delegated tokens), never by the request.

## Error messages and logs

Validation errors and logs reach people and systems that may not be allowed to see the data of a run.

- Error messages of servers MUST name the location of the error (a JSON Pointer relative to `workflow_params`, see [WES](adoption/wes.md)) and the rule that failed (or the schema's `x-ga4gh-error-message`). They SHOULD NOT repeat the value that failed.
- Servers MUST NOT include contents of data files (e.g., cells of a sample sheet) in error messages or logs.
- Servers SHOULD log validation failures with the same redaction as error messages.

## Validation of data files on the server

The profile's checks apply to `workflow_params`. Checking the contents of files that the request refers to, such as the rows of a sample sheet described by `x-ga4gh-tabular-schema`, is OPTIONAL, and validation of tabular files is deferred in version 0.3 (see [#17](https://github.com/uniqueg/ga4gh-io-schema/issues/17)).

A server that reads data files to validate them becomes a data accessor:

- It MUST access the files with the user's delegated credentials, not with credentials of its own.
- It MUST run where the access conditions of the data allow processing (e.g., in the data's jurisdiction or inside the TRE that holds it).
- It is subject to the same audit and logging rules as the workflow itself, and it MUST apply size limits before reading a file.

Clients SHOULD NOT download data files into a browser to validate them (see [Tabular data and cloud sovereignty](specification/keywords.md#tabular-data-and-cloud-sovereignty)).

## Related sections

- [Server-side validation in WES](adoption/wes.md): how servers validate `workflow_params` and report errors.
- [Non-goals](motivation.md#non-goals-and-out-of-scope-the-defenses): hardware
  limits are a server-side policy, not a schema validation task.
