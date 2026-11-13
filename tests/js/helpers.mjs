// SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud / GA4GH Contributors
// SPDX-License-Identifier: Apache-2.0

// Shared setup of the JavaScript tests: the schemas of the repository, read
// from the local copies, and the validators, set up offline as
// docs/tools/javascript.md describes.

import { readFileSync, readdirSync } from "node:fs";

import { removeUriSchemePlugin } from "@hyperjump/browser";
import { setShouldValidateFormat } from "@hyperjump/json-schema/draft-2020-12";
import "@hyperjump/json-schema/formats";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

export const ROOT = new URL("../../", import.meta.url);
export const SCHEMAS = new URL("schemas/", ROOT);
export const SUITE = new URL("tests/conformance/schema-documents/", ROOT);
export const EXAMPLES = new URL("tests/data/", ROOT);
export const DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema";

/** Read and parse a JSON file. */
export const readJson = (url) => JSON.parse(readFileSync(url, "utf-8"));

/** Return the `*.schema.json` documents of a directory, sorted by name. */
export const documents = (dir) =>
  readdirSync(dir)
    .filter((name) => name.endsWith(".schema.json"))
    .sort()
    .map((name) => [name, readJson(new URL(name, dir))]);

export const PROFILE = readJson(
  new URL("ga4gh-io-profile.schema.json", SCHEMAS),
);
export const VOCABULARY_SCHEMAS = documents(
  new URL("vocabularies/", SCHEMAS),
).map(([, schema]) => schema);

/**
 * Return an Ajv instance: the 2020-12 build, formats asserted
 * (ajv-formats), and the vocabularies of the profile added from the local
 * copies, so that nothing is fetched. The caller adds the profile, as a
 * schema or as a meta-schema.
 *
 * @param {object} options - Options of Ajv.
 */
export function newAjv(options) {
  const ajv = new Ajv2020(options);
  addFormats(ajv);
  for (const schema of VOCABULARY_SCHEMAS) ajv.addSchema(schema);
  return ajv;
}

/**
 * Set up @hyperjump/json-schema offline: retrieval over HTTP(S) turned off,
 * formats asserted. Its registry is global, so each test file registers its
 * schemas once.
 */
export function setUpHyperjump() {
  removeUriSchemePlugin("http");
  removeUriSchemePlugin("https");
  setShouldValidateFormat(true);
}
