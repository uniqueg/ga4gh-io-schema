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

* `x-ga4gh-output-glob` *(string)*: A glob, relative to the output directory of the run, that finds an output (a file reference or a list of them) among the files of a run when the engine doesn't report the output by name (e.g., Nextflow and Snakemake in current WES servers); it is ignored when the engine does. See [Outputs](outputs.md#x-ga4gh-output-glob). *Relation to nf-schema: none; `nextflow_schema.json` describes parameters only.*

* `x-ga4gh-ontology` *(string, uri)*: Maps an input or output to a formal ontology term for its data (e.g., the EDAM data term `http://edamontology.org/data_2044`, *Sequence*), enabling semantic linking and automated reasoning. The format of a referenced file (e.g., an EDAM format term) goes into `ontology` of [`x-ga4gh-file`](files.md).

* `x-ga4gh-ui-widget` *(string)*: A hint for web portals to render a specific component. *Relation to nf-schema: `nf-schema` has no widget keyword (see its [list of keys](https://nextflow-io.github.io/nf-schema/latest/nextflow_schema/nextflow_schema_specification/)); form controls in its ecosystem follow from a parameter's `type` and `format`. This profile adds an explicit hint from a GA4GH vocabulary (e.g., `slider`, `table-viewer`). Generic JSON Schema form libraries don't read it, so portals need an adapter (see [Portals and clients](../adoption/portals.md)).* The meta-schema rejects widgets that the vocabulary doesn't have, except `custom:<name>`; clients render a parameter whose widget they don't know (e.g., a `custom:` widget of another platform) by its `type` and `format`, and offer outputs without a known viewer for download. Version 0.3 removed the `password` widget (see [Secrets](../security.md#secrets)) and defers viewers other than `table-viewer` and `html-viewer` (see [Roadmap](../roadmap.md#deferred)).

* `x-ga4gh-tabular-schema` *(object, experimental)*: A nested JSON schema describing the expected array/object structure of an opaque tabular file, as a hint for clients (see [Tabular data and cloud sovereignty](#tabular-data-and-cloud-sovereignty)). *Relation to nf-schema: Corresponds to `nf-schema`'s `schema` key, which points to a schema for a sample sheet; nf-schema validates the file with it, the profile doesn't (yet). nf-schema's `uniqueEntries` has no equivalent (see *Uniqueness* in [Leveraging native JSON Schema](#leveraging-native-json-schema-what-we-dont-reinvent)). We explicitly namespace it as `x-ga4gh-tabular-schema` to prevent standard JSON Schema validators from confusing it with standard object `properties` or the `$schema` keyword.*

* `x-ga4gh-description-format` *(string)*: Indicates the formatting of the standard `description` field (accepted values: `plain_text` (default) and `markdown`, which means CommonMark with a few named extensions, see [Markdown descriptions](#markdown-descriptions); version 0.3 removed `rst`, see [Roadmap](../roadmap.md#cut), and clients show descriptions in any other format as plain text, see [Rendering schemas and outputs](../security.md#rendering-schemas-and-outputs)). *Relation to nf-schema: Equivalent in intent to the `help_text` property, but relies on formatting the standard JSON Schema `description` field rather than creating a secondary text property.*

* `x-ga4gh-hidden` *(boolean)*: Signals UI generators to hide this parameter under "Advanced" toggles, except where users must set it (see [Hidden inputs](#hidden-inputs)). *Relation to nf-schema: Equivalent to the `hidden` property.*

* `x-ga4gh-error-message` *(string)*: A custom, human-readable error message to display if payload validation fails, in place of the validator's message, for failures at the location of the value that the schema describes (see [Error messages](#error-messages)). *Relation to nf-schema: Equivalent to the `errorMessage` property.*

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

### Markdown descriptions

With `"x-ga4gh-description-format": "markdown"`, the `description` of the
schema is [CommonMark](https://spec.commonmark.org/0.31.2/) (version 0.31.2)
with these changes:

* **Raw HTML is text.** HTML blocks and inline HTML (e.g., `<b>`,
  `<script>`, `<img src=x onerror=...>`) are not interpreted: clients MUST
  show them as the literal characters of the source, escaped, as if they
  were in a code span. They are neither passed to the page nor removed.
  Entity and numeric character references (e.g., `&amp;`) are decoded as
  CommonMark defines.
* **Images are not rendered.** Clients MUST show the alt text of an image
  (e.g., `![Workflow diagram](https://example.org/diagram.png)` shows
  "Workflow diagram") as text, and MUST NOT load the image.
* **Links only with allowed schemes.** Clients MUST render a link (inline,
  reference or autolink) as a link only if its destination is an absolute
  URI whose scheme is on the client's allow-list (see
  [Rendering schemas and outputs](../security.md#rendering-schemas-and-outputs)).
  Other links, including relative ones, which have no base to resolve
  against, are shown as their link text.
* **Extensions:** of the
  [GitHub Flavored Markdown](https://github.github.com/gfm/) extensions,
  only *tables*, *strikethrough* and *autolinks* (extended: `www.` and bare
  `https://` URLs) are allowed. Clients MAY support them; a client that
  doesn't shows them as CommonMark, i.e., as the text of the source. Task
  list items, footnotes, math, diagrams, front matter and other extensions
  are not part of the format: clients MUST NOT render them as such (they
  come out as the CommonMark rendering of their source), and authors
  SHOULD NOT use them.

The rules make the subset safe to render: a client meets the Markdown rules
of [Rendering schemas and outputs](../security.md#rendering-schemas-and-outputs)
with an option of its CommonMark library that escapes raw HTML (e.g.,
`html: false` of markdown-it) and with renderers of its own for images,
which write the alt text, and for links, which check the destination; it
doesn't need an HTML sanitiser for descriptions. Turning off images in a
library is not enough where the library then shows the image as a link
(e.g., markdown-it). Markdown reads well as plain text, so clients without a
Markdown renderer MAY show such descriptions as plain text.

For example, the description of this input has a link, an image and raw
HTML:

```json
{
  "type": "string",
  "description": "Reads in **FASTQ** format, see [the format](https://en.wikipedia.org/wiki/FASTQ_format).\n\n![Quality plot](https://example.org/plot.png)\n\n<b onclick=\"alert(1)\">Paired-end</b> reads go into two files.",
  "x-ga4gh-description-format": "markdown",
  "x-ga4gh-file": {"kind": "file"}
}
```

A conforming client renders it as (in HTML; the link is kept if `https` is
on its allow-list):

```html
<p>Reads in <strong>FASTQ</strong> format, see <a href="https://en.wikipedia.org/wiki/FASTQ_format">the format</a>.</p>
<p>Quality plot</p>
<p>&lt;b onclick=&quot;alert(1)&quot;&gt;Paired-end&lt;/b&gt; reads go into two files.</p>
```

The `<b>` element comes out as text, with its attribute, and no image is
loaded.

### Hidden inputs

`"x-ga4gh-hidden": true` marks an input that most users don't need to
change, e.g., a tuning parameter with a good default. Form renderers MAY
show such inputs only on request (e.g., under "Advanced").

An input that users must set can't be hidden: the form couldn't be
submitted until the user found it. An input must be set if it is listed in
`required` of the object that contains it and no `default` gives it a value
(neither the `default` of its own schema nor one of an enclosing schema);
for an input inside an optional object, this applies once the object is
set.

* Form renderers MUST show an input that must be set with the inputs that
  aren't hidden, as if its `x-ga4gh-hidden` were `false`.
* Form renderers MUST show a hidden input, with its error, when its value
  fails validation.
* Schema documents SHOULD NOT set `"x-ga4gh-hidden": true` on inputs that
  must be set. The meta-schema doesn't reject them: whether an input is
  required is stated in `required` of the enclosing object, not in the
  schema of the input, and JSON Schema can't compare the names in
  `required` with the schemas in `properties`.

### Error messages

`x-ga4gh-error-message` is the text that users see when a value fails
validation, in place of the message of the validator.

* **Scope:** the message of a schema covers the failures at the location of
  the value that the schema applies to: failures of its own keywords and of
  the subschemas that it applies to the same value (`allOf`, `anyOf`,
  `oneOf`, `not`, `if`, `then`, `else`, `dependentSchemas`, `$ref`,
  `$dynamicRef`). It doesn't cover failures of other values, such as the
  values of properties or the items of an array: they get the message of
  their own schema, if any. The location of a failure is the instance
  location
  ([JSON Schema Core, §12.3.3](https://json-schema.org/draft/2020-12/json-schema-core#section-12.3.3))
  of the schema that contains the keyword that failed. A missing property
  is a failure of `required`, a keyword of the object, so it gets the
  message of the object's schema, not that of the property; likewise, a
  property that `"additionalProperties": false` rejects is a failure of
  `additionalProperties` at the location of the object (the schema `false`
  has no keywords, and no message).
* **Precedence:** if more than one schema with a message applies to the
  location of a failure (e.g., the schema of a property, with a message,
  refers with `$ref` to a definition with a message of its own), the
  outermost of them is used, i.e., the one nearest to the root of the IO
  schema on the evaluation path: it is the most specific to the parameter,
  while definitions are shared. Of schemas at the same depth (e.g., branches
  of `anyOf`), the first in the document is used.
* **Replacement:** the message replaces the validator's messages of all the
  failures that it covers, and is given once per location, however many
  keywords fail there. Form renderers SHOULD show it with the input; they
  MAY offer the validator's messages on request (e.g., to authors of
  schemas). WES servers return it in `msg` of the `ErrorResponse`, after
  the JSON Pointer of the location (see [WES](../adoption/wes.md)).
  Failures that no message covers get a message built from the location and
  the keyword that failed.

For example, with this IO schema:

```json
{
  "$schema": "https://raw.githubusercontent.com/uniqueg/ga4gh-io-schema/v0.3.0/schemas/ga4gh-io-profile.schema.json",
  "type": "object",
  "properties": {
    "inputs": {
      "type": "object",
      "properties": {
        "samples": {
          "type": "array",
          "items": {"$ref": "#/$defs/sample_id"},
          "minItems": 1,
          "x-ga4gh-error-message": "Give at least one sample"
        },
        "control": {
          "$ref": "#/$defs/sample_id",
          "x-ga4gh-error-message": "The control is a sample ID such as S1"
        }
      },
      "required": ["samples"]
    }
  },
  "$defs": {
    "sample_id": {
      "type": "string",
      "pattern": "^S[0-9]+$",
      "x-ga4gh-error-message": "Sample IDs are S followed by digits, e.g., S1"
    }
  }
}
```

a WES server that validates `"workflow_params": {"samples": []}` returns
the message of `samples`, which covers `minItems`:

```json
{
  "msg": "/samples: Give at least one sample",
  "status_code": 400
}
```

For `{"samples": ["S1", "x2"]}`, the failing value is an item, which the
message of `samples` doesn't cover; the item's schema is the definition,
whose message is used:

```json
{
  "msg": "/samples/1: Sample IDs are S followed by digits, e.g., S1",
  "status_code": 400
}
```

For `{"samples": ["S1"], "control": "c1"}`, both `control` and the
definition that it refers to have a message for the location `/control`;
the outer one, of `control`, is used:

```json
{
  "msg": "/control: The control is a sample ID such as S1",
  "status_code": 400
}
```

For `{}`, the failure is the `required` of the inputs object, which has no
message: the server builds the message from the location and the keyword
that failed.
