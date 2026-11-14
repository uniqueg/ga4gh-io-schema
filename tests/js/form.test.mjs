// SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud / GA4GH Contributors
// SPDX-License-Identifier: Apache-2.0

// Tests the logic of the form proof of concept (examples/form/form.js),
// without a browser: the controls that inputs get, hidden inputs, and how
// the text of the controls becomes the values that the host turns into
// `workflow_params` (tests/test_form_host.py tests the host).

import assert from "node:assert/strict";
import { describe, test } from "node:test";

import {
  controlOf,
  describeFields,
  dropUntouched,
  fieldForError,
  formatValue,
  parseValue,
  pointerOf,
  resolve,
  setAt,
} from "../../examples/form/form.js";
import { readJson } from "./helpers.mjs";

const DEMO = readJson(new URL("../../examples/demo/ga4gh-io.schema.json", import.meta.url));
const DEMO_VALUES = readJson(new URL("../../examples/demo/values.json", import.meta.url));

/**
 * Collect values as the form does: from the text of each control.
 *
 * @param {Array<object>} fields The fields.
 * @param {Map<string, *>} raw The text of the controls, by field name.
 * @returns {object} The values.
 */
function collect(fields, raw) {
  const values = {};
  const walk = (list) => {
    for (const field of list) {
      if (field.children) walk(field.children);
      else if (raw.has(field.name)) setAt(values, field.path, parseValue(field, raw.get(field.name)));
    }
  };
  walk(fields);
  return values;
}

describe("demo schema", () => {
  const fields = describeFields(DEMO, DEMO.properties.inputs);

  test("gets the controls of the demo docs", () => {
    assert.deepEqual(
      fields.map(({ name, label, control, required, hidden }) => ({ name, label, control, required, hidden })),
      [
        { name: "reads", label: "Aligned reads (BAM)", control: "file", required: true, hidden: false },
        { name: "min_mapq", label: "Minimum mapping quality", control: "slider", required: false, hidden: false },
        { name: "read_filter", label: "Read filter", control: "radio", required: false, hidden: false },
      ],
    );
  });

  test("prefills the defaults", () => {
    assert.deepEqual(
      fields.map((field) => formatValue(field, field.defaultValue)),
      ["", "0", "0"],
    );
  });

  test("turns the controls into the values of values.json", () => {
    const raw = new Map([
      ["reads", DEMO_VALUES.reads],
      ["min_mapq", "20"],
      ["read_filter", "1"],
    ]);
    assert.deepEqual(collect(fields, raw), DEMO_VALUES);
  });

  test("leaves unset inputs out, and keeps text that isn't a number", () => {
    const raw = new Map([
      ["reads", ""],
      ["min_mapq", "high"],
      ["read_filter", ""],
    ]);
    assert.deepEqual(collect(fields, raw), { min_mapq: "high" });
  });
});

describe("controls", () => {
  const cases = [
    [{ type: "string" }, "text"],
    [{ type: "string", "x-ga4gh-ui-widget": "textarea" }, "textarea"],
    [{ type: "string", "x-ga4gh-ui-widget": "color-picker" }, "color"],
    [{ type: "string", format: "date", "x-ga4gh-ui-widget": "date-picker" }, "date"],
    [{ type: "string", "x-ga4gh-ui-widget": "custom:other" }, "text"],
    [{ type: "string", "x-ga4gh-ui-widget": "slider" }, "text"],
    [{ type: "integer" }, "number"],
    [{ type: ["number", "null"], minimum: 0, maximum: 1, "x-ga4gh-ui-widget": "slider" }, "slider"],
    [{ type: "boolean" }, "boolean-select"],
    [{ type: "boolean", default: false, "x-ga4gh-ui-widget": "switch" }, "checkbox"],
    [{ type: "string", enum: ["a", "b"] }, "select"],
    [{ enum: [1, "a"], "x-ga4gh-ui-widget": "radio" }, "radio"],
    [{ type: "array", items: { type: "string" }, "x-ga4gh-ui-widget": "tags" }, "lines"],
    [{ type: "array", items: { type: "string", enum: ["x", "y"] } }, "multiselect"],
    [{ type: "array", items: { type: "object" } }, "json"],
    [{ type: "array" }, "json"],
    [{ type: "object", properties: { a: { type: "string" } } }, "object"],
    [{ type: "object" }, "json"],
    [{ type: "string", "x-ga4gh-file": { kind: "directory" } }, "file"],
    [{ anyOf: [{ type: "string", "x-ga4gh-file": { kind: "file" } }, { type: "string" }] }, "file"],
    [{ anyOf: [{ type: "integer" }, { type: "string" }] }, "json"],
  ];
  for (const [schema, control] of cases) {
    test(`${JSON.stringify(schema)} -> ${control}`, () => {
      assert.equal(controlOf(schema), control);
    });
  }
});

describe("values", () => {
  const field = (schema) => ({ control: controlOf(schema), schema });

  test("of each control", () => {
    assert.equal(parseValue(field({ type: "boolean", default: true }), true), true);
    assert.equal(parseValue(field({ type: "boolean" }), ""), undefined);
    assert.equal(parseValue(field({ type: "boolean" }), "false"), false);
    assert.equal(parseValue(field({ enum: [1, "a"] }), "0"), 1);
    assert.deepEqual(parseValue(field({ type: "array", items: { enum: ["x", "y"] } }), ["1"]), ["y"]);
    assert.equal(parseValue(field({ type: "array", items: { enum: ["x"] } }), []), undefined);
    assert.equal(parseValue(field({ type: "number" }), " 1.5 "), 1.5);
    assert.deepEqual(parseValue(field({ type: "array", items: { type: "string" } }), "a\n\n b \n"), ["a", "b"]);
    assert.deepEqual(parseValue(field({ type: "array", items: { type: "integer" } }), "1\n2"), [1, 2]);
    assert.equal(parseValue(field({ type: "array", items: { type: "string" } }), " \n"), undefined);
    assert.deepEqual(parseValue(field({ type: "object" }), '{"a": 1}'), { a: 1 });
    assert.equal(parseValue(field({ type: "object" }), "{"), "{");
    assert.equal(parseValue(field({ type: "object" }), ""), undefined);
    assert.equal(parseValue(field({ type: "string" }), "x"), "x");
  });

  test("format back into the controls", () => {
    assert.equal(formatValue(field({ type: "boolean" }), true), "true");
    assert.equal(formatValue(field({ type: "boolean" }), undefined), "");
    assert.equal(formatValue(field({ type: "boolean", default: true }), true), true);
    assert.equal(formatValue(field({ enum: ["a"] }), "z"), "");
    assert.deepEqual(formatValue(field({ type: "array", items: { enum: ["x", "y"] } }), ["y"]), ["1"]);
    assert.equal(formatValue(field({ type: "array", items: { type: "string" } }), ["a", "b"]), "a\nb");
    assert.equal(formatValue(field({ type: "object" }), { a: 1 }), '{\n  "a": 1\n}');
    assert.equal(formatValue(field({ type: "object" }), undefined), "");
  });
});

describe("hidden inputs and nested objects", () => {
  const root = {
    $defs: { threads: { type: "integer", "x-ga4gh-hidden": true } },
    properties: {
      inputs: {
        type: "object",
        properties: {
          reference: { type: "string", "x-ga4gh-file": { kind: "file" }, "x-ga4gh-hidden": true },
          threads: { $ref: "#/$defs/threads", default: 4 },
          index: { type: "string", "x-ga4gh-hidden": true },
          options: {
            type: "object",
            default: { mode: "fast" },
            properties: { mode: { type: "string", "x-ga4gh-hidden": true } },
            required: ["mode"],
          },
        },
        required: ["reference", "threads"],
      },
    },
  };
  const fields = describeFields(root, root.properties.inputs);

  test("shows hidden inputs that users must set", () => {
    const hidden = Object.fromEntries(fields.map(({ name, hidden }) => [name, hidden]));
    assert.deepEqual(hidden, { reference: false, threads: true, index: true, options: false });
    // A default of the enclosing object gives `mode` a value
    assert.equal(fields[3].children[0].hidden, true);
    assert.equal(fields[3].children[0].defaultValue, "fast");
  });

  test("nests values and finds the field of an error", () => {
    const values = collect(fields, new Map([["mode", "slow"], ["threads", "2"]]));
    assert.deepEqual(values, { threads: 2, options: { mode: "slow" } });
    assert.equal(fieldForError(fields, "/options/mode").name, "mode");
    assert.equal(fieldForError(fields, "/options").name, "options");
    assert.equal(fieldForError(fields, "/threads").name, "threads");
    assert.equal(fieldForError(fields, ""), undefined);
    assert.equal(fieldForError(fields, "/thread"), undefined);
  });

  test("resolves local references only", () => {
    assert.deepEqual(resolve(root, { $ref: "#/$defs/threads", default: 4 }), {
      type: "integer",
      "x-ga4gh-hidden": true,
      default: 4,
    });
    const external = { $ref: "https://example.org/x.json" };
    assert.equal(resolve(root, external), external);
  });
});

describe("review cases", () => {
  test("follows references in items and unions", () => {
    const root = {
      $defs: { e: { type: "string", enum: ["x", "y"] }, file: { type: "string", "x-ga4gh-file": { kind: "file" } } },
      properties: {
        inputs: {
          properties: {
            picks: { type: "array", items: { $ref: "#/$defs/e" } },
            data: { anyOf: [{ $ref: "#/$defs/file" }, { type: "string" }] },
          },
        },
      },
    };
    const [picks, data] = describeFields(root, root.properties.inputs);
    assert.equal(picks.control, "multiselect");
    assert.deepEqual(parseValue(picks, ["1"]), ["y"]);
    assert.equal(data.control, "file");
  });

  test("keeps numbers that aren't JSON numbers as text", () => {
    const field = { control: "lines", schema: { type: "array", items: { type: "integer" } } };
    assert.deepEqual(parseValue(field, "0x10\n0b11\n-2e3"), ["0x10", "0b11", -2000]);
    assert.equal(parseValue({ control: "number", schema: {} }, "Infinity"), "Infinity");
    assert.equal(parseValue({ control: "number", schema: {} }, "1e400"), "1e400");
    assert.equal(parseValue({ control: "number", schema: {} }, ".5"), 0.5);
    assert.equal(parseValue({ control: "number", schema: {} }, "+1."), 1);
  });

  test("leaves out optional objects at their defaults", () => {
    const root = {
      properties: {
        inputs: {
          properties: {
            adv: {
              type: "object",
              properties: { flag: { type: "boolean", default: false }, name: { type: "string" } },
              required: ["name"],
            },
            req: { type: "object", properties: { flag: { type: "boolean", default: false } } },
          },
          required: ["req"],
        },
      },
    };
    const fields = describeFields(root, root.properties.inputs);
    const untouched = { adv: { flag: false }, req: { flag: false } };
    dropUntouched(fields, untouched);
    assert.deepEqual(untouched, { req: { flag: false } });
    const nested = {
      properties: {
        inputs: {
          properties: {
            adv: {
              type: "object",
              properties: {
                name: { type: "string" },
                inner: { type: "object", properties: { flag: { type: "boolean", default: false } } },
              },
              required: ["name", "inner"],
            },
          },
        },
      },
    };
    const deep = { adv: { inner: { flag: false } }, list: [1] };
    dropUntouched(describeFields(nested, nested.properties.inputs), deep);
    assert.deepEqual(deep, { list: [1] });
    const changed = { adv: { flag: true } };
    dropUntouched(fields, changed);
    assert.deepEqual(changed, { adv: { flag: true } });
  });
});

test("pointers escape special characters", () => {
  assert.equal(pointerOf(["a/b", "c~d", 0]), "/a~1b/c~0d/0");
});
