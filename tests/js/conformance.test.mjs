// SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud / GA4GH Contributors
// SPDX-License-Identifier: Apache-2.0

// Runs the conformance suite (tests/conformance/schema-documents/) and the
// examples (tests/data/) through JavaScript validators, offline: every
// document in valid/ and every example must be accepted, every document in
// invalid/ rejected, as by the Python validator (tests/test_conformance.py).
// Each validator is set up the way the documentation describes (see
// docs/tools/javascript.md).

import assert from "node:assert/strict";
import { describe, test } from "node:test";

import { validate } from "@hyperjump/json-schema/draft-2020-12";

import {
  DRAFT_2020_12,
  EXAMPLES,
  PROFILE,
  SUITE,
  documents,
  namesProfile,
  newAjv,
  registerProfile,
} from "./helpers.mjs";

const VALID = [...documents(new URL("valid/", SUITE)), ...documents(EXAMPLES)];
const INVALID = documents(new URL("invalid/", SUITE));

/**
 * Return Ajv's compiled check of the profile (see newAjv()).
 *
 * @param {object} options - Options of Ajv.
 */
function ajvCheck(options) {
  const ajv = newAjv(options);
  ajv.addSchema(PROFILE);
  return ajv.getSchema(PROFILE.$id);
}

/**
 * Return a function that validates a document against the profile with Ajv,
 * after checking its `$schema` (see namesProfile()).
 *
 * @param {object} options - Options of Ajv.
 */
function ajvValidator(options) {
  const check = ajvCheck(options);
  return async (document) => namesProfile(document) && check(document);
}

/**
 * Return a function that validates a document against the profile with
 * @hyperjump/json-schema, offline (see setUpHyperjump()), with the profile
 * and its vocabularies registered from the local copies, after checking its
 * `$schema` (see namesProfile()).
 */
function hyperjumpValidator() {
  registerProfile();
  return async (document) =>
    namesProfile(document) && (await validate(PROFILE.$id, document)).valid;
}

for (const [name, setUp] of [
  ["Ajv (strict: false)", () => ajvValidator({ strict: false })],
  [
    "Ajv (strict: false, allErrors: true)",
    () => ajvValidator({ strict: false, allErrors: true }),
  ],
  // Strict mode, except for the two checks that the profile can't meet (see
  // docs/tools/javascript.md).
  [
    "Ajv (strict: true, strictTypes: false, strictRequired: false)",
    () =>
      ajvValidator({ strict: true, strictTypes: false, strictRequired: false }),
  ],
  ["@hyperjump/json-schema", hyperjumpValidator],
]) {
  describe(name, () => {
    const isValid = setUp();
    for (const [file, document] of VALID) {
      test(`accepts ${file}`, async () => {
        assert.equal(await isValid(document), true);
      });
    }
    for (const [file, document] of INVALID) {
      test(`rejects ${file}`, async () => {
        assert.equal(await isValid(document), false);
      });
    }
  });
}

// A nested error must not make validators that report all errors flag the
// keywords of the enclosing schemas as unevaluated: only the unknown
// x-ga4gh-* keyword is unevaluated.
describe("errors of a nested unknown keyword", () => {
  const document = {
    $schema: PROFILE.$id,
    properties: {
      inputs: {
        type: "object",
        properties: {
          a: {
            type: "object",
            "x-ga4gh-hidden": true,
            properties: { b: { "x-ga4gh-bogus": 1 } },
          },
        },
      },
    },
  };

  test("Ajv (allErrors: true) reports only the unknown keyword", () => {
    const check = ajvCheck({ strict: false, allErrors: true });
    assert.equal(check(document), false);
    const unevaluated = check.errors
      .filter((error) => error.keyword === "unevaluatedProperties")
      .map((error) => error.params.unevaluatedProperty);
    assert.deepEqual([...new Set(unevaluated)], ["x-ga4gh-bogus"]);
  });

  test("@hyperjump/json-schema reports only the unknown keyword", async () => {
    registerProfile();
    const output = await validate(PROFILE.$id, document, "BASIC");
    assert.equal(output.valid, false);
    // hyperjump reports the failing `false` of unevaluatedProperties at the
    // location of the property.
    assert.ok(output.errors.length > 0);
    for (const error of output.errors) {
      assert.match(error.instanceLocation, /\/x-ga4gh-bogus$/);
    }
  });
});

// The meta-schema doesn't require `$schema`, because hyperjump removes it
// before it checks a schema against its dialect (see values.test.mjs); the
// runners above check it first (namesProfile()), which is why they reject
// missing-schema.schema.json of the suite. A `$schema` that names another
// meta-schema still fails the meta-schema.
describe("$schema", () => {
  const document = { properties: { inputs: { type: "object" } } };
  const foreign = { ...document, $schema: DRAFT_2020_12 };

  test("the profile accepts a document without $schema", async () => {
    assert.equal(ajvCheck({ strict: false })(document), true);
    registerProfile();
    assert.equal((await validate(PROFILE.$id, document)).valid, true);
  });

  test("the profile rejects a $schema that names another meta-schema", async () => {
    assert.equal(ajvCheck({ strict: false })(foreign), false);
    registerProfile();
    assert.equal((await validate(PROFILE.$id, foreign)).valid, false);
  });

  test("the runners reject a document without $schema", () => {
    const missing = INVALID.find(([file]) => file === "missing-schema.schema.json");
    assert.equal(ajvCheck({ strict: false })(missing[1]), true);
    assert.equal(namesProfile(missing[1]), false);
    assert.equal(namesProfile(document), false);
    assert.equal(namesProfile({ ...document, $schema: PROFILE.$id }), true);
  });
});
