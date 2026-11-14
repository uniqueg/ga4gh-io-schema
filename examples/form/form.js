// SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud / GA4GH Contributors
// SPDX-License-Identifier: Apache-2.0

// The logic of the form proof of concept, without the DOM: which control
// each input of an IO schema gets, and how the text of a control becomes a
// value. `io-schema-form.js` renders the fields; `tests/js/form.test.mjs`
// tests this module with Node.js. See docs/adoption/form.md for the scope.

/**
 * Resolve a local `$ref` (`#/...`) of a schema, merging the referring
 * schema's own keywords over the target's. Other references are left as
 * they are.
 *
 * @param {object} root The IO schema.
 * @param {*} schema A subschema.
 * @returns {*} The subschema with its local references resolved.
 */
export function resolve(root, schema) {
  let current = schema;
  for (let depth = 0; depth < 32; depth += 1) {
    const ref = current?.$ref;
    if (typeof ref !== "string" || !ref.startsWith("#")) return current;
    const target = ref
      .slice(1)
      .split("/")
      .slice(1)
      .map((part) => decodeURIComponent(part).replaceAll("~1", "/").replaceAll("~0", "~"))
      .reduce((node, part) => node?.[part], root);
    const { $ref: _ignored, ...rest } = current;
    current = { ...target, ...rest };
  }
  return current;
}

/**
 * The single type of a schema, ignoring `"null"` in a type array.
 *
 * @param {object} schema A subschema.
 * @returns {string|undefined} The type.
 */
function typeOf(schema) {
  const types = [schema.type].flat().filter((type) => type && type !== "null");
  return types.length === 1 ? types[0] : undefined;
}

/**
 * Choose the control of an input, by widget, then by type, `format` and
 * `enum`. Each type checks only its own widgets, so widgets that don't fit
 * the schema, or that the form doesn't know, are ignored. `json` is the
 * fallback: a text area for the value as JSON.
 *
 * @param {object} schema The input's schema, with references resolved.
 * @returns {string} The control.
 */
export function controlOf(schema) {
  const type = typeOf(schema);
  const widget = schema["x-ga4gh-ui-widget"];
  const file =
    schema["x-ga4gh-file"] !== undefined ||
    (schema.anyOf ?? []).some((branch) => branch?.["x-ga4gh-file"] !== undefined);
  if (file) return "file";
  // `radio` and `dropdown` fit any type with `enum`
  if (Array.isArray(schema.enum)) return widget === "radio" ? "radio" : "select";
  switch (type) {
    case "boolean":
      return schema.default === undefined ? "boolean-select" : "checkbox";
    case "integer":
    case "number":
      return widget === "slider" ? "slider" : "number";
    case "string":
      if (widget === "textarea") return "textarea";
      if (widget === "color-picker") return "color";
      if (schema.format === "date") return "date";
      return "text";
    case "array": {
      const items = schema.items ?? {};
      if (Array.isArray(items.enum)) return "multiselect";
      if (["string", "number", "integer"].includes(typeOf(items))) return "lines";
      return "json";
    }
    case "object":
      return schema.properties ? "object" : "json";
    default:
      return "json";
  }
}

/**
 * Describe the fields of an object schema, recursively: one field per
 * property, with the control, the label and whether it is hidden. A hidden
 * input that users must set (required, and no default gives it a value) is
 * shown, as the guide for portals requires.
 *
 * @param {object} root The IO schema.
 * @param {object} schema An object schema, e.g., `inputs`.
 * @param {Array<string>} path Location of the object in the values.
 * @param {object} [defaults] Default of the object, from an enclosing schema.
 * @returns {Array<object>} The fields.
 */
export function describeFields(root, schema, path = [], defaults = undefined) {
  const object = resolve(root, schema);
  const required = new Set(object.required ?? []);
  const objectDefaults = object.default ?? defaults;
  return Object.entries(object.properties ?? {}).map(([name, property]) => {
    const resolved = resolve(root, property);
    const defaultValue = resolved.default ?? objectDefaults?.[name];
    const isRequired = required.has(name);
    const control = controlOf(resolved);
    const field = {
      name,
      path: [...path, name],
      label: typeof resolved.title === "string" ? resolved.title : name,
      description: typeof resolved.description === "string" ? resolved.description : "",
      control,
      required: isRequired,
      hidden:
        resolved["x-ga4gh-hidden"] === true &&
        !(isRequired && defaultValue === undefined),
      defaultValue,
      schema: resolved,
    };
    if (control === "object") {
      field.children = describeFields(root, resolved, field.path, defaultValue);
    }
    return field;
  });
}

/**
 * Turn the text of a control into a value. `undefined` means unset: the
 * input is left out of the values. Text that doesn't parse is kept as text,
 * so that validation reports it.
 *
 * @param {object} field The field.
 * @param {string|boolean|Array<string>} raw The control's value: text, the
 *   state of a checkbox, or the indexes of the chosen options.
 * @returns {*} The value.
 */
export function parseValue(field, raw) {
  const { control, schema } = field;
  switch (control) {
    case "checkbox":
      return raw === true;
    case "boolean-select":
      return raw === "" ? undefined : raw === "true";
    case "select":
    case "radio":
      return raw === "" ? undefined : schema.enum[Number(raw)];
    case "multiselect":
      return raw.length ? raw.map((index) => schema.items.enum[Number(index)]) : undefined;
    case "number":
    case "slider":
      return raw.trim() === "" ? undefined : toNumber(raw.trim());
    case "lines": {
      const numeric = ["number", "integer"].includes(typeOf(schema.items ?? {}));
      const lines = raw
        .split("\n")
        .map((line) => line.trim())
        .filter((line) => line !== "");
      if (!lines.length) return undefined;
      return numeric ? lines.map(toNumber) : lines;
    }
    case "json":
      if (raw.trim() === "") return undefined;
      try {
        return JSON.parse(raw);
      } catch {
        return raw;
      }
    default:
      return raw === "" ? undefined : raw;
  }
}

/**
 * Turn the value of a field into the text of its control, e.g., to prefill
 * a default.
 *
 * @param {object} field The field.
 * @param {*} value The value.
 * @returns {string|boolean|Array<string>} Text, a checkbox state, or the
 *   indexes of the chosen options.
 */
export function formatValue(field, value) {
  const { control, schema } = field;
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  switch (control) {
    case "checkbox":
      return value === true;
    case "boolean-select":
      return value === undefined ? "" : String(value);
    case "select":
    case "radio": {
      const index = schema.enum.findIndex((option) => same(option, value));
      return index < 0 ? "" : String(index);
    }
    case "multiselect":
      return (value ?? []).map((item) =>
        String(schema.items.enum.findIndex((option) => same(option, item))),
      );
    case "lines":
      return (value ?? []).join("\n");
    case "json":
      return value === undefined ? "" : JSON.stringify(value, null, 2);
    default:
      return value === undefined ? "" : String(value);
  }
}

/**
 * Parse a number, or keep the text if it isn't one.
 *
 * @param {string} text The text.
 * @returns {number|string} The number, or the text.
 */
function toNumber(text) {
  const number = Number(text);
  return Number.isFinite(number) ? number : text;
}

/**
 * Set a value at a location in the values, creating the enclosing objects.
 *
 * @param {object} values The values.
 * @param {Array<string>} path The location.
 * @param {*} value The value; `undefined` leaves the values unchanged.
 */
export function setAt(values, path, value) {
  if (value === undefined) return;
  let node = values;
  for (const key of path.slice(0, -1)) {
    node[key] ??= {};
    node = node[key];
  }
  node[path.at(-1)] = value;
}

/**
 * Turn a location into a JSON Pointer (RFC 6901).
 *
 * @param {Array<string|number>} path The location.
 * @returns {string} The JSON Pointer.
 */
export function pointerOf(path) {
  return path.map((part) => `/${String(part).replaceAll("~", "~0").replaceAll("/", "~1")}`).join("");
}

/**
 * Find the field that shows an error: the field at the error's location,
 * or the nearest enclosing one (e.g., the list of an item that fails). An
 * error at the location of the values as a whole (e.g., a missing required
 * input) has no field.
 *
 * @param {Array<object>} fields The fields, at any depth.
 * @param {string} pointer Location of the error, as a JSON Pointer.
 * @returns {object|undefined} The field.
 */
export function fieldForError(fields, pointer) {
  let best;
  for (const field of fields) {
    const own = pointerOf(field.path);
    if (pointer === own || pointer.startsWith(`${own}/`)) {
      best = field;
      if (field.children) best = fieldForError(field.children, pointer) ?? field;
    }
  }
  return best;
}
