# Keywords

## Input architecture and the extension vocabulary

To maintain maximum compatibility with existing libraries (e.g., UI form generators, LLMs), the profile strictly relies on JSON Schema Draft 2020-12.

### Leveraging native JSON Schema (what we don't reinvent)

Where workflow languages have historically invented proprietary keywords, schemas use native JSON Schema features:

* **File Paths and References:** Instead of proprietary file types, schemas MUST use the native string formats: `{"type": "string", "format": "uri"}`.

* **Mimetypes:** Instead of custom `mimetype` properties, schemas MUST use the native `contentMediaType` keyword.

* **Uniqueness:** Where all items of an array have to differ, schemas MUST use the native `uniqueItems: true`. This is not the same as `nf-schema`'s `uniqueEntries`, which requires the *combination of the values of given keys* to be unique across the objects of an array (e.g., a unique `sample_id` per row of a sample sheet): with `uniqueItems`, two rows with the same `sample_id` but different other values both pass. The profile has no equivalent of `uniqueEntries` yet.

### Tabular data and cloud sovereignty

Workflows heavily rely on tabular data (e.g., CSV sample sheets). Validating these files before a run prevents time-wasting and potentially expensive pipeline failures. To facilitate this, the profile introduces `x-ga4gh-tabular-schema`—a nested JSON array definition that describes the internal row/column structure of a CSV/TSV file.

Per the JSON Schema specification, standard client libraries ignore `x-` annotations because they are unrecognized extension keywords. To actively validate a CSV against this schema, a platform needs a custom parser.

Here, the roles of the client side and the server side have to be kept apart to preserve cloud data sovereignty. Forcing a generic web UI to download a massive, potentially sensitive patient sample sheet (e.g., fetched via a DRS URI) directly into the user's browser just to run client-side validation violates the data perimeter. Instead, UIs can use the `x-ga4gh-tabular-schema` as a *hint* to auto-generate an interactive spreadsheet grid for the user to fill out *before* saving it to the cloud. Meanwhile, the execution side can validate the file before it starts the run. This is optional, and reading the file makes the server a data accessor, with the user's delegated credentials and within the data's access conditions (see [Validation of data files on the server](../security.md#validation-of-data-files-on-the-server)).

See also [Security considerations](../security.md).

### The `x-ga4gh-*` vocabulary

We propose the following initial set of custom annotations to support execution semantics and dynamic UIs. Where applicable, we explicitly map these to their conceptual origins in the Nextflow ecosystem (`nf-schema`) to acknowledge prior art and ease adoption.

* `x-ga4gh-drs-uri` *(boolean)*: Indicates if a string URI is expected to be a valid Data Repository Service (DRS) identifier. While the `drs://` URI scheme often makes this explicit at runtime, this flag allows UIs to proactively render a DRS-specific data browser or resolution widget before a user provides input.

* `x-ga4gh-ontology` *(string, uri)*: Maps an input or output to a formal ontology term (e.g., `http://edamontology.org/format_1929`), enabling semantic linking and automated reasoning.

* `x-ga4gh-ui-widget` *(string)*: A hint for web portals to render a specific component. *Relation to nf-schema: `nf-schema` has no widget keyword (see its [list of keys](https://nextflow-io.github.io/nf-schema/latest/nextflow_schema/nextflow_schema_specification/)); form controls in its ecosystem follow from a parameter's `type` and `format`. This profile adds an explicit hint from a GA4GH vocabulary (e.g., `slider`, `genome-browser`). Generic JSON Schema form libraries don't read it, so portals need an adapter (see [Portals and clients](../adoption/portals.md)).*

* `x-ga4gh-tabular-schema` *(object)*: A nested JSON schema dictating the expected array/object structure of an opaque tabular file. *Relation to nf-schema: Functionally equivalent to `nf-schema`'s ability to apply a schema to a samplesheet. We explicitly namespace it as `x-ga4gh-tabular-schema` to prevent standard JSON Schema validators from confusing it with standard object `properties` or the `$schema` keyword.*

* `x-ga4gh-fa-icon` *(string)*: FontAwesome icon class to display next to the parameter in dynamic UIs. *Relation to nf-schema: Equivalent to the `fa_icon` property.*

* `x-ga4gh-description-format` *(string)*: Indicates the formatting of the standard `description` field (accepted values: `plain_text` (default), `markdown`, `rst`; `rst` is removed in version 0.3, see [#17](https://github.com/uniqueg/ga4gh-io-schema/issues/17), and clients show it as plain text, see [Rendering schemas and outputs](../security.md#rendering-schemas-and-outputs)). *Relation to nf-schema: Equivalent in intent to the `help_text` property, but relies on formatting the standard JSON Schema `description` field rather than creating a secondary text property.*

* `x-ga4gh-hidden` *(boolean)*: Signals UI generators to hide this parameter under "Advanced" toggles. *Relation to nf-schema: Equivalent to the `hidden` property.*

* `x-ga4gh-error-message` *(string)*: A custom, human-readable error message to display if payload validation fails. *Relation to nf-schema: Equivalent to the `errorMessage` property.*

The keywords and the vocabulary of UI widgets are defined in the
[meta-schema](meta-schema.md), which checks them in every schema of an IO
schema, at any depth, and rejects other keywords that start with `x-ga4gh-`
(see [Structure of the meta-schema](meta-schema.md#structure-of-the-meta-schema)
for the allowed values and the vocabulary file of each keyword).
