# UI widgets

`x-ga4gh-ui-widget` tells clients how to render an input or an output (see
[Keywords](keywords.md#the-x-ga4gh-vocabulary)). Its values come from the
vocabulary of UI widgets
([`ui-widgets.schema.json`](https://github.com/uniqueg/ga4gh-io-schema/blob/main/schemas/vocabularies/ui-widgets.schema.json)),
or are custom widgets (`custom:<name>`). This page defines, for each widget
of the vocabulary, the schemas that it fits, the keywords that it needs, and
the value that it produces. Requirements use the key words of BCP 14, as
described in [Notational conventions](conformance.md#notational-conventions).

The vocabulary has two groups: *input widgets*, which edit the value of an
input, and *output viewers*, which show an output of a run. Input widgets
are for `inputs`, viewers for `outputs`.

## Input widgets

| Widget | `type` | Needs, in the same schema | Value |
| ----- | ----- | ----- | ----- |
| `text` | `string` | | A string, entered on one line |
| `textarea` | `string` | | A string, which may contain line breaks |
| `number` | `integer` or `number` | | A JSON number; an integer for `integer` |
| `slider` | `integer` or `number` | `minimum` or `exclusiveMinimum`, and `maximum` or `exclusiveMaximum` | A JSON number within the bounds; the step is `multipleOf`, if set, else 1 for `integer` and the client's choice for `number` |
| `dropdown` | any | `enum`; or, for a multiple choice, `"type": "array"` and `items` with `enum` | One of the values of `enum`; for an array, an array of values of `items.enum` (schemas SHOULD add `"uniqueItems": true`) |
| `radio` | any | `enum` | One of the values of `enum` |
| `typeahead` | `string` | `enum` or `examples` | With `enum`: one of its values, offered as the user types. Without `enum`: any string; the values of `examples` are suggestions only |
| `checkbox` | `boolean` | | `true` or `false` |
| `switch` | `boolean` | | `true` or `false` |
| `date-picker` | `string` | `"format": "date"` | An RFC 3339 `full-date`, e.g., `2026-11-12` |
| `time-picker` | `string` | `"format": "time"` | An RFC 3339 `full-time`, with offset, e.g., `14:30:00Z`; the offset is that of the time zone that the widget shows to the user (by default, the user's local one), so the value names the same moment for every client |
| `datetime-picker` | `string` | `"format": "date-time"` | An RFC 3339 `date-time`, e.g., `2026-11-12T14:30:00Z` |
| `color-picker` | `string` | | A colour as `#rrggbb`, six lowercase hexadecimal digits (the value of an HTML `<input type="color">`, e.g., `#1f77b4`); schemas SHOULD add `"pattern": "^#[0-9a-f]{6}$"` |
| `file-picker` | `string` | `x-ga4gh-file` with `"kind": "file"` | A file reference to a file (see [Values](files.md#values)) |
| `directory-picker` | `string` | `x-ga4gh-file` with `"kind": "directory"` | A file reference to a directory (see [Values](files.md#values)) |
| `tags` | `array` | `items` with `"type": "string"` | An array of strings, one per tag, never a delimited string. With `items.enum`, only its values; otherwise any strings |

`type` may also be an array of the type and `"null"` (e.g.,
`["string", "null"]`), except for file references, which are strings, and
the items of `tags`; the widget then also lets users clear the value, which
gives `null`, but only where `null` passes the schema (e.g., with `enum`,
only if `null` is one of its values). Labels of
the values of `enum` (e.g., with `oneOf` and `const`) are not part of
version 0.3: clients show the values themselves.

## Output viewers

| Widget | Schema | Shows |
| ----- | ----- | ----- |
| `html-viewer` | a file reference with `"kind": "file"` (e.g., `"mediaType": "text/html"`) | The HTML file in a sandboxed frame |
| `table-viewer` | a file reference with `"kind": "file"` (e.g., `"mediaType": "text/csv"` or `text/tab-separated-values`) | The tabular file as a table, with escaped cells |

A viewer goes on the schema of the file reference itself: for a list of
files, on `items`; for files keyed by sample, on `additionalProperties`
(see [Values](outputs.md#values)). The rules for showing outputs are in
[Rendering schemas and outputs](../security.md#rendering-schemas-and-outputs);
outputs without a viewer, or with one that the client doesn't know, are
offered for download. Version 0.3 defers other viewers (see
[Roadmap](../roadmap.md#deferred)).

## Rules

* **Same schema:** the keywords that a widget needs MUST be in the schema
  that carries the widget, not only in a schema that it refers to (`$ref`)
  or that applies at the same location (e.g., `allOf`). Clients and the
  meta-schema then find them without resolving anything. For example,
  `{"$ref": "#/$defs/count", "x-ga4gh-ui-widget": "slider"}` is rejected
  even if `count` has a type and bounds; the `type` and the bounds go next
  to the widget.
* **What the meta-schema checks:** for every schema, at any depth, the
  `type`, `format`, bounds, `enum` or `examples`, `x-ga4gh-file` and
  `items` that the tables require. For the parameters directly under
  `inputs` and `outputs` (not deeper, and not in `$defs`), it also rejects
  viewers on inputs and input widgets on outputs. It doesn't check whether the values of `enum` have
  the type of the schema, whether a colour has a `pattern`, the group of
  widgets in nested schemas and definitions (e.g., a viewer on a property of
  an object input), or custom widgets. Validators report a misfit at the
  keyword that doesn't fit (e.g., `type`, with "not valid under any of the
  given schemas"), not at the widget: the widget is what asks for it.
* **Widgets that don't fit:** a client that gets a widget that doesn't fit
  its schema (e.g., a viewer in a nested input, or a schema that wasn't
  validated) MUST render the input as it renders inputs of the same type
  without a widget hint, as it does for widgets that it doesn't know.
  Viewers on inputs, and input widgets on outputs, are ignored.
* **Values:** a client that renders an input with a widget of the
  vocabulary MUST produce values as the last column of
  [Input widgets](#input-widgets) defines, and checks them against the
  schema, as any other value (see
  [Request builder](conformance.md#request-builder)).
* **Without a widget,** clients choose the control by `type`, `format` and
  `enum`.

For example, a slider for a fraction and a set of tags:

```json
{
  "min_quality": {
    "type": "number",
    "minimum": 0,
    "maximum": 1,
    "multipleOf": 0.05,
    "default": 0.5,
    "x-ga4gh-ui-widget": "slider"
  },
  "labels": {
    "type": "array",
    "items": {"type": "string", "enum": ["tumour", "normal", "control"]},
    "uniqueItems": true,
    "x-ga4gh-ui-widget": "tags"
  }
}
```

The conformance suite has a valid case with every widget
(`valid/ui-widgets`) and a negative case for each mismatch that the
meta-schema detects (`invalid/ui-widget-*`; see
[Conformance suite](conformance.md#conformance-suite)).
