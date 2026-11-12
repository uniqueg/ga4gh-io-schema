# Security considerations

This page states the requirements for schemas, servers and clients that use the profile, so that they handle schemas, requests, data and outputs safely. The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [BCP 14](https://www.rfc-editor.org/info/bcp14) ([RFC 2119](https://www.rfc-editor.org/rfc/rfc2119), [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)) when, and only when, they appear in all capitals, as shown here.

Roles, as used on this page:

- **Server:** a WES implementation or gateway that validates run requests against IO schemas.
- **Client:** a portal, other user interface, or AI agent that renders forms from IO schemas, builds run requests, or shows the outputs of runs.
- **Execution side:** the server and the workflow engine it runs, including the components that stage data for a run.

The requirements on this page are part of the [conformance classes](specification/conformance.md#conformance-classes) (see there for how the roles map to the classes). Validating requests against IO schemas is optional for a WES server (see [WES](adoption/wes.md)); the requirements for servers apply to every server that does.

## Validation is not a security boundary

Validation in the client catches mistakes before a run starts, which saves time and compute; it is not a security boundary. A client can be bypassed, and anyone with access to the API can `POST` any request directly. Servers MUST NOT rely on validation by the client. Validation against an IO schema checks the shape of a request; it doesn't replace the checks of the execution side (e.g., against shell injection in the engine, or limits on resources), which remain the responsibility of the server and the workflow engine.

## Sources of schemas

A schema decides what a server accepts and which addresses a validator may look up, so it has to come from a source that the deployment trusts.

- Servers MUST use only IO schemas from trusted sources: the TRS entry of the workflow (see [TRS](adoption/trs.md)) in a registry that the deployment trusts, or a schema bundled with the deployment.
- Servers MUST NOT accept IO schemas supplied by clients in a run request. Earlier versions of this proposal let servers use schemas that came with the request; version 0.3 removes that (see [Roadmap](roadmap.md#cut) and [#17](https://github.com/uniqueg/ga4gh-io-schema/issues/17)).
- Servers MUST NOT retrieve any reference (`$ref` or `$dynamicRef`) over the network while validating, whatever the base URI (`$id`) of the schema. Network lookups would make the server send requests to addresses chosen by the schema's author, including internal addresses such as `169.254.169.254` (the metadata service of many cloud providers) or services behind the firewall; a valid URI is not a safe address.
- A schema with a reference that the server can't resolve from its local copies is invalid. Servers MUST NOT validate requests against it, not even partially, and MUST NOT pass requests for that workflow to the engine unchecked: they reject them (fail closed) with a message that names the problem with the schema, and SHOULD report it to the operators of the deployment.
- IO schemas MUST be bundled: all references are local (`#/$defs/…`) or point to the profile's meta-schema and vocabularies. Validators MUST load the meta-schema and vocabularies from local copies (as the [validator](tools/validator.md) does), not from the network.

## Regular expressions and size limits

The `pattern` and `patternProperties` keywords run regular expressions from the schema on values from the request. Some expressions take time that grows exponentially with the length of the input when matched by a backtracking engine.

- Schemas SHOULD use only the subset of the ECMA-262 dialect that JSON Schema recommends ([JSON Schema Core, §6.4](https://json-schema.org/draft/2020-12/json-schema-core#section-6.4)) and SHOULD avoid nested quantifiers (e.g., `(a+)+`).
- Servers MUST either match regular expressions with an engine that runs in linear time (e.g., [RE2](https://github.com/google/re2)) or limit the time spent on validation of a request. A request whose validation exceeds the limit is rejected, not passed to the engine.
- Servers SHOULD reject schemas with patterns longer than a limit set by the deployment (e.g., 1,000 characters).
- Servers MUST limit the size of the `workflow_params` they validate (e.g., 1 MiB) and SHOULD limit the depth of nested values; requests above the limits are rejected before validation.

## URIs and file references

The `uri` format of JSON Schema accepts any scheme of [RFC 3986](https://www.rfc-editor.org/rfc/rfc3986), including `javascript:`, `data:` and `file:`. Validation against `format: uri` therefore doesn't make a reference safe to use, and many validators don't check formats at all.

Schemas MUST mark every file input and output as a [file reference](specification/files.md) (`x-ga4gh-file`), and servers and clients treat every value of a file reference as one: also a value where a file reference is one branch of `anyOf` or `oneOf`, and the `default`, `const`, `enum` and `examples` of a file reference. [File references](specification/files.md#values) defines the values; in short:

- The annotation's `schemes` can narrow the allow-list below for a parameter, but never extend it.
- Paths without a scheme are values of inputs only, and not allowed where the annotation has `schemes`.
- File references in the rows of tabular files (e.g., sample sheets) never reach the server: the execution side MUST check them by the rules below after staging the file and before the engine runs, or enforce the rules for hosts with network controls (see [File references in tabular files](specification/files.md#file-references-in-tabular-files)).

The rules below apply to all of them.

- Servers and clients MUST check the scheme of every file reference, in inputs and in outputs, against an allow-list before they use it: before staging an input, and before showing an output as a link or loading it into a viewer.
- The allow-list is set by the deployment. It SHOULD contain only `drs` and `https`; the object-store schemes that the deployment supports (e.g., `s3`, `gs`); and `http`, only for internal networks.
- `javascript`, `data` and other schemes that run code in a browser MUST NOT be on the allow-list, and clients MUST NOT show references with them as links.
- `file` URIs and paths without a scheme refer to the file system of the execution side. Servers MUST NOT accept them in inputs, except: paths relative to the files attached to the run request (`workflow_attachment`), and, in deployments with a shared file system, paths in directories that the deployment explicitly allows. Servers MUST reject paths with `..` segments, and MUST check that the path, after normalising it and resolving symbolic links, lies inside the attachments or an allowed directory. Clients MUST NOT show such paths as links.
- Before staging an input, the execution side MUST make sure that it connects only to hosts that the deployment allows, for the first request and for every redirect. Loopback, link-local (e.g., `169.254.169.254`) and private address ranges MUST be rejected unless the deployment explicitly allows them. Checking the scheme alone doesn't prevent requests to internal services, and checking a name before connecting doesn't either (the name can resolve to another address when the connection is made). Workflow engines usually stage data with their own HTTP and object-store clients, which follow redirects without such checks; deployments therefore SHOULD enforce the rule with network controls for egress (e.g., an egress proxy or a network policy that denies these ranges), or connect only to the address they checked.

## Rendering schemas and outputs

Text in an IO schema comes from the author of the workflow, and outputs come from the run, which may have processed files supplied by users. Clients MUST treat both as untrusted.

The viewers below are values of `x-ga4gh-ui-widget` on outputs, from the profile's vocabulary of UI widgets (see [Meta-schema](specification/meta-schema.md)). The rules apply by content: they also apply to HTML, Markdown or tabular outputs without a widget hint.

- **Text:** Clients MUST show `title`, `description`, enumeration values and `x-ga4gh-error-message` as text. If `x-ga4gh-description-format` is `markdown`, clients MUST render the Markdown with a sanitiser that removes raw HTML, scripts and event handlers, and that allows only links with schemes on the allow-list; images and other embedded resources are removed, or loaded only from origins that the client allows or through a proxy of the client. Descriptions in any other format, including `rst` (removed in version 0.3, see [Roadmap](roadmap.md#cut); reStructuredText has directives that embed raw HTML or include files), MUST be shown as plain text. Raw HTML in descriptions MUST NOT reach the page, whatever the format.
- **Links:** Clients MUST check every link, in descriptions and outputs, against the allow-list of schemes before showing it. Clients MUST NOT link directly to outputs that they don't show in a viewer: the stored file may have active content (e.g., HTML, SVG or PDF) whatever its name, and would open unsandboxed on the origin of the storage. They offer such outputs for download, through a proxy that sets `Content-Disposition: attachment` and `X-Content-Type-Options: nosniff`, or with a download link that makes the storage set them (e.g., the `response-content-disposition` parameter of a presigned URL).
- **HTML outputs (`html-viewer`):** Clients MUST show HTML outputs only in an `iframe` with an empty `sandbox` attribute (no tokens: no scripts, forms, pop-ups or navigation of the top window; this also gives the frame an opaque origin), and with a Content Security Policy (sent with the document, or, for `srcdoc`, as a `<meta>` element placed before the untrusted markup) that blocks loading of external resources (e.g., `default-src 'none'; img-src data:; style-src 'unsafe-inline'`). Otherwise, they offer them for download only. HTML outputs are often built from files supplied by users (e.g., labels from a sample sheet), so a report from a trusted workflow can still contain markup from users, and external images or styles would tell a third party when and from where a report was viewed.
- **Tables (`table-viewer`):** Clients MUST escape the cells of tables.

Version 0.3 supports only download, tables and sandboxed HTML; the other viewers of earlier versions (`markdown-viewer`, `pdf-viewer`, `genome-browser`, `scatter-plot`) are removed from the vocabulary and deferred (see [Roadmap](roadmap.md#deferred)). Clients offer outputs with deferred or unknown viewers for download only, as for links to active content above.

## Access to data

Clients identify input data; the execution side fetches it.

- Clients SHOULD submit inputs held in a Data Repository Service (DRS) as `drs://` identifiers in `workflow_params`, not as resolved access URLs.
- Clients MUST NOT put signed URLs, access tokens or other credentials in `workflow_params`. WES returns the request, including `workflow_params`, in the run log ([`RunLog.request`](https://github.com/ga4gh/workflow-execution-service-schemas/blob/1.1.0/openapi/workflow_execution_service.openapi.yaml)); parameters also end up in the logs of the engine and in provenance records such as RO-Crates; and signed URLs can expire while the run waits in the queue.
- The execution side MUST resolve the identifiers itself, when it stages the data, with credentials delegated by the user (e.g., a token exchanged for the run, or GA4GH Passports), and only after the server has checked the request.
- The execution side MUST send delegated credentials only to DRS servers that the deployment trusts, as tokens restricted to that server (audience-restricted); identifiers of other DRS servers are rejected before they are resolved. This applies also to compact identifiers (`drs://prefix:accession`), which are resolved through a resolver service: the check applies to the DRS server that the resolver returns.

**Compatibility:** WES deployments that can't resolve DRS identifiers on the execution side can't run workflows with such inputs under this flow. They SHOULD say so (e.g., in their service information) rather than accept resolved URLs from clients.

This replaces the flow of earlier versions, in which the client resolved DRS identifiers and passed the resulting URLs to WES. See also [Portals and clients](adoption/portals.md#data-repository-service-drs-interplay).

## Secrets

- Workflow parameters are not a channel for secrets: schemas MUST NOT define inputs for passwords, API keys, tokens or other credentials. Version 0.3 removed the `password` value of `x-ga4gh-ui-widget` from the vocabulary (see [Roadmap](roadmap.md#cut)), so the meta-schema rejects it; the rule also covers inputs that the meta-schema can't recognise as secrets, e.g., a `custom:` widget or `"format": "password"`.
- Credentials that a workflow needs are provided by the deployment (e.g., a secret store of the execution side, or delegated tokens), never by the request.

## Error messages and logs

Validation errors and logs reach people and systems that may not be allowed to see the data of a run.

- Error messages of servers MUST name the location of the error (a JSON Pointer relative to `workflow_params`, see [WES](adoption/wes.md)) and the rule that failed, or the `x-ga4gh-error-message` that covers the failure (see [Error messages](specification/keywords.md#error-messages)). They SHOULD NOT repeat the value that failed.
- Servers MUST NOT include contents of data files (e.g., cells of a sample sheet) in error messages or logs.
- Servers SHOULD log validation failures with the same redaction as error messages.

## Validation of data files on the server

The profile's checks apply to `workflow_params`. Checking the contents of files that the request refers to, such as the rows of a sample sheet described by `x-ga4gh-tabular-schema`, is OPTIONAL, and validation of tabular files is deferred in version 0.3 (see [Roadmap](roadmap.md#deferred)).

A server that reads data files to validate them becomes a data accessor:

- It MUST access the files with the user's delegated credentials, not with credentials of its own.
- It MUST run where the access conditions of the data (the terms under which the data may be used, e.g., a data access agreement) allow processing, e.g., in the data's jurisdiction or inside the Trusted Research Environment (TRE) that holds it.
- It MUST log its access to the files as the deployment requires for the workflow itself.
- It MUST apply size limits before reading a file.

Clients SHOULD NOT download data files into a browser to validate them (see [Tabular data and cloud sovereignty](specification/keywords.md#tabular-data-and-cloud-sovereignty)).

## Related sections

- [Server-side validation in WES](adoption/wes.md): how servers validate `workflow_params` and report errors.
- [Tabular data and cloud sovereignty](specification/keywords.md#tabular-data-and-cloud-sovereignty):
  which validation of sample sheets belongs on the client and which on the
  execution side.
- [Non-goals](motivation.md#non-goals-and-out-of-scope-the-defenses): hardware
  limits are a server-side policy, not a schema validation task.
