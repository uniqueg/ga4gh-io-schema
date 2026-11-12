// SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud / GA4GH Contributors
// SPDX-License-Identifier: Apache-2.0

// Runs the conformance suite (tests/conformance/schema-documents/) and the
// examples (tests/data/) through JavaScript validators, offline: every
// document in valid/ and every example must be accepted, every document in
// invalid/ rejected, as by the Python validator (tests/test_conformance.py).
// Each validator is set up the way the documentation describes (see
// docs/tools/javascript.md).

import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { describe, test } from "node:test";

import { removeUriSchemePlugin } from "@hyperjump/browser";
import {
  registerSchema,
  setShouldValidateFormat,
  validate,
} from "@hyperjump/json-schema/draft-2020-12";
import "@hyperjump/json-schema/formats";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

const ROOT = new URL("../../", import.meta.url);
const SCHEMAS = new URL("schemas/", ROOT);
const VOCABULARIES = new URL("vocabularies/", SCHEMAS);
const SUITE = new URL("tests/conformance/schema-documents/", ROOT);
const EXAMPLES = new URL("tests/data/", ROOT);

const readJson = (url) => JSON.parse(readFileSync(url, "utf-8"));

/** Return the `*.schema.json` documents of a directory, sorted by name. */
const documents = (dir) =>
  readdirSync(dir)
    .filter((name) => name.endsWith(".schema.json"))
    .sort()
    .map((name) => [name, readJson(new URL(name, dir))]);

const PROFILE = readJson(new URL("ga4gh-io-profile.schema.json", SCHEMAS));
const VOCABULARY_SCHEMAS = documents(VOCABULARIES).map(([, schema]) => schema);
const VALID = [...documents(new URL("valid/", SUITE)), ...documents(EXAMPLES)];
const INVALID = documents(new URL("invalid/", SUITE));

/**
 * Return a function that validates a document against the profile with Ajv:
 * the 2020-12 build, formats asserted (ajv-formats), the profile and its
 * vocabularies added from the local copies, so that nothing is fetched.
 *
 * @param {object} options - Options of Ajv.
 */
function ajvValidator(options) {
  const ajv = new Ajv2020(options);
  addFormats(ajv);
  for (const schema of VOCABULARY_SCHEMAS) ajv.addSchema(schema);
  ajv.addSchema(PROFILE);
  const check = ajv.getSchema(PROFILE.$id);
  return async (document) => check(document);
}

/**
 * Return a function that validates a document against the profile with
 * @hyperjump/json-schema: formats asserted, retrieval over HTTP(S) turned
 * off, the profile and its vocabularies registered from the local copies.
 */
function hyperjumpValidator() {
  removeUriSchemePlugin("http");
  removeUriSchemePlugin("https");
  setShouldValidateFormat(true);
  for (const schema of VOCABULARY_SCHEMAS) registerSchema(schema);
  registerSchema(PROFILE);
  return async (document) => (await validate(PROFILE.$id, document)).valid;
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
