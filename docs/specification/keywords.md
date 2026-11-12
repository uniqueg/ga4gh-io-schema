# Keywords

## Input architecture and the extension vocabulary

To maintain maximum compatibility with existing libraries (e.g., UI form generators, LLMs), the profile strictly relies on JSON Schema Draft 2020-12.

### Leveraging native JSON Schema (what we don't reinvent)

Where workflow languages have historically invented proprietary keywords, schemas use native JSON Schema features:

* **File Paths and References:** A file or directory is a string with the `x-ga4gh-file` annotation, not a proprietary type or object: `{"type": "string", "x-ga4gh-file": {"kind": "file"}}`. JSON Schema has no keyword for references to files: `format: uri` rejects relative paths and compact DRS identifiers, can't tell files from directories and carries no index files, and `contentMediaType` describes the string itself, not the file it refers to. See [File references](files.md).

* **Uniqueness:** Where all items of an array have to differ, schemas MUST use the native `uniqueItems: true`. This is not the same as `nf-schema`'s `uniqueEntries`, which requires the *combination of the values of given keys* to be unique across the objects of an array (e.g., a unique `sample_id` per row of a sample sheet): with `uniqueItems`, two rows with the same `sample_id` but different other values both pass. The profile has no equivalent of `uniqueEntries` yet.

### Tabular data and cloud sovereignty

Workflows heavily rely on tabular data (e.g., CSV sample sheets). The profile has `x-ga4gh-tabular-schema`, a nested JSON Schema that describes the rows of a CSV/TSV file. In version 0.3, the keyword is **experimental** and a *hint* for clients, not a validation rule: validation of tabular files is deferred (see [Roadmap](../roadmap.md#deferred)). It needs rules for turning text cells into typed values, for empty cells and for dialects, which [Frictionless Table Schema](../related-work.md#frictionless-table-schema) already defines; a later version may adopt Table Schema by reference instead.

Per the JSON Schema specification, standard client libraries ignore `x-` annotations because they are unrecognized extension keywords. A platform that wants to check a file against the hint needs a parser of its own.

Here, the roles of the client side and the server side have to be kept apart to preserve cloud data sovereignty. Forcing a generic web UI to download a massive, potentially sensitive patient sample sheet (e.g., fetched via a DRS URI) directly into the user's browser just to run client-side validation violates the data perimeter. Instead, UIs can use the `x-ga4gh-tabular-schema` as a *hint* to auto-generate an interactive spreadsheet grid for the user to fill out *before* saving it to the cloud. A server MAY check the file before it starts the run. This is optional, and reading the file makes the server a data accessor, with the user's delegated credentials and within the data's access conditions (see [Validation of data files on the server](../security.md#validation-of-data-files-on-the-server)).

See also [Security considerations](../security.md).

### The `x-ga4gh-*` vocabulary

We propose the following initial set of custom annotations to support execution semantics and dynamic UIs. Where applicable, we explicitly map these to their conceptual origins in the Nextflow ecosystem (`nf-schema`) to acknowledge prior art and ease adoption.

* `x-ga4gh-file` *(object)*: Marks a string as a reference to a file or directory: its kind, the media type, format term and compression of the referenced file, its required secondary files (e.g., indexes) and the URI schemes that values may use (e.g., `drs` for Data Repository Service identifiers, so that UIs can offer a DRS browser before a user provides input). See [File references](files.md). *Relation to nf-schema: replaces `format: file-path`, `directory-path` and `path`, and the `mimetype` property.* It replaces `x-ga4gh-drs-uri` of version 0.2 (`"schemes": ["drs"]`).

* `x-ga4gh-ontology` *(string, uri)*: Maps an input or output to a formal ontology term for its data (e.g., the EDAM data term `http://edamontology.org/data_2044`, *Sequence*), enabling semantic linking and automated reasoning. The format of a referenced file (e.g., an EDAM format term) goes into `ontology` of [`x-ga4gh-file`](files.md).

* `x-ga4gh-ui-widget` *(string)*: A hint for web portals to render a specific component. *Relation to nf-schema: `nf-schema` has no widget keyword (see its [list of keys](https://nextflow-io.github.io/nf-schema/latest/nextflow_schema/nextflow_schema_specification/)); form controls in its ecosystem follow from a parameter's `type` and `format`. This profile adds an explicit hint from a GA4GH vocabulary (e.g., `slider`, `table-viewer`). Generic JSON Schema form libraries don't read it, so portals need an adapter (see [Portals and clients](../adoption/portals.md)).* The meta-schema rejects widgets that the vocabulary doesn't have, except `custom:<name>`; clients render a parameter whose widget they don't know (e.g., a `custom:` widget of another platform) by its `type` and `format`, and offer outputs without a known viewer for download. Version 0.3 removed the `password` widget (see [Secrets](../security.md#secrets)) and defers viewers other than `table-viewer` and `html-viewer` (see [Roadmap](../roadmap.md#deferred)).

* `x-ga4gh-tabular-schema` *(object, experimental)*: A nested JSON schema describing the expected array/object structure of an opaque tabular file, as a hint for clients (see [Tabular data and cloud sovereignty](#tabular-data-and-cloud-sovereignty)). *Relation to nf-schema: Corresponds to `nf-schema`'s `schema` key, which points to a schema for a sample sheet; nf-schema validates the file with it, the profile doesn't (yet). nf-schema's `uniqueEntries` has no equivalent (see *Uniqueness* in [Leveraging native JSON Schema](#leveraging-native-json-schema-what-we-dont-reinvent)). We explicitly namespace it as `x-ga4gh-tabular-schema` to prevent standard JSON Schema validators from confusing it with standard object `properties` or the `$schema` keyword.*

* `x-ga4gh-description-format` *(string)*: Indicates the formatting of the standard `description` field (accepted values: `plain_text` (default) and `markdown`; version 0.3 removed `rst`, see [Roadmap](../roadmap.md#cut), and clients show descriptions in any other format as plain text, see [Rendering schemas and outputs](../security.md#rendering-schemas-and-outputs)). *Relation to nf-schema: Equivalent in intent to the `help_text` property, but relies on formatting the standard JSON Schema `description` field rather than creating a secondary text property.*

* `x-ga4gh-hidden` *(boolean)*: Signals UI generators to hide this parameter under "Advanced" toggles. *Relation to nf-schema: Equivalent to the `hidden` property.*

* `x-ga4gh-error-message` *(string)*: A custom, human-readable error message to display if payload validation fails. *Relation to nf-schema: Equivalent to the `errorMessage` property.*

* `x-ga4gh-parameter` *(object)*: Binds a property of `inputs` or `outputs` to the engine's parameter: its `name` relative to the entry point, where it differs from the property name, and its `type` as declared in the workflow language (see [Parameter bindings](identity.md#parameter-bindings)). *Relation to nf-schema: none; Nextflow parameters have the names of the properties.*

* `x-ga4gh-workflow` *(object, top level only)*: Ties the IO schema to a workflow version in a TRS and to its engine: TRS tool and version ids, descriptor type and version, path and checksum of the primary descriptor, and the entry point (see [The workflow block](identity.md#the-workflow-block)). *Relation to nf-schema: none; a `nextflow_schema.json` lives in the repository of its pipeline and isn't tied to a version by its content.*

The keywords and the vocabulary of UI widgets are defined in the
[meta-schema](meta-schema.md), which checks them in every schema of an IO
schema, at any depth, and rejects other keywords that start with `x-ga4gh-`
(see [Structure of the meta-schema](meta-schema.md#structure-of-the-meta-schema)
for the allowed values and the vocabulary file of each keyword). Version 0.3
removed `x-ga4gh-fa-icon`: icons are a choice of the portal, not part of the
contract (see [Roadmap](../roadmap.md#cut)); the meta-schema rejects it like
any other unknown `x-ga4gh-*` keyword.
