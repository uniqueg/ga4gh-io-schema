// SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud / GA4GH Contributors
// SPDX-License-Identifier: Apache-2.0

// Validates input values against `inputs` of the examples (tests/data/)
// with JavaScript validators, offline, as tests/test_examples.py does in
// Python: with the semantics of JSON Schema Draft 2020-12, whatever the
// `$schema` of the IO schema (see docs/specification/keywords.md and
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
const EXAMPLES = new URL("tests/data/", ROOT);

const DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema";

const readJson = (url) => JSON.parse(readFileSync(url, "utf-8"));

const PROFILE = readJson(new URL("ga4gh-io-profile.schema.json", SCHEMAS));
const VOCABULARY_SCHEMAS = readdirSync(VOCABULARIES)
  .filter((name) => name.endsWith(".schema.json"))
  .map((name) => readJson(new URL(name, VOCABULARIES)));
const TOOL = readJson(new URL("example_tool.schema.json", EXAMPLES));
const WORKFLOW = readJson(new URL("example_workflow.schema.json", EXAMPLES));

// Input values; the valid ones are those of tests/test_examples.py.
const CASES = [
  [
    "valid tool inputs",
    TOOL,
    {
      reference_fasta: "s3://example-bucket/refs/GRCh38.fa",
      read_1: "drs://dg.4503:6ca5c2a8-1a2b-4c3d-9e8f-0a1b2c3d4e5f",
      read_2: "https://data.example.org/runs/1/reads_2.fastq.gz",
      threads: 8,
    },
    true,
  ],
  [
    "valid workflow inputs",
    WORKFLOW,
    {
      sample_manifest: "drs://drs.example.org/314159",
      genome_index: "s3://example-bucket/refs/GRCh38-index/",
    },
    true,
  ],
  ["no workflow inputs", WORKFLOW, {}, false],
  [
    "workflow input of the wrong type",
    WORKFLOW,
    { sample_manifest: "drs://drs.example.org/314159", genome_index: 3 },
    false,
  ],
  [
    "unknown workflow input",
    WORKFLOW,
    {
      sample_manifest: "drs://drs.example.org/314159",
      genome_index: "s3://example-bucket/refs/GRCh38-index/",
      no_such_input: "x",
    },
    false,
  ],
];

/** Return the URI of `inputs` of an IO schema. */
const inputsUri = (schema) => `${schema.$id}#/properties/inputs`;

/**
 * Return a function that validates values against `inputs` of an IO schema
 * with Ajv: the profile is added as a meta-schema, so that Ajv accepts IO
 * schemas that name it in `$schema` (and checks them against it).
 */
function ajvValidator() {
  const ajv = new Ajv2020({ strict: false });
  addFormats(ajv);
  for (const schema of VOCABULARY_SCHEMAS) ajv.addSchema(schema);
  ajv.addMetaSchema(PROFILE);
  ajv.addSchema(TOOL);
  ajv.addSchema(WORKFLOW);
  return async (schema, values) => ajv.validate(inputsUri(schema), values);
}

/**
 * Return a function that validates values against `inputs` of an IO schema
 * with @hyperjump/json-schema: the IO schemas are registered as copies that
 * name the Draft 2020-12 dialect in `$schema`. hyperjump removes `$schema`
 * from a schema before it checks the schema against its dialect, so the
 * profile's meta-schema, which requires `$schema`, would reject every IO
 * schema.
 */
function hyperjumpValidator() {
  removeUriSchemePlugin("http");
  removeUriSchemePlugin("https");
  setShouldValidateFormat(true);
  for (const schema of [TOOL, WORKFLOW]) {
    registerSchema({ ...schema, $schema: DRAFT_2020_12 });
  }
  return async (schema, values) =>
    (await validate(inputsUri(schema), values)).valid;
}

for (const [name, setUp] of [
  ["Ajv", ajvValidator],
  ["@hyperjump/json-schema", hyperjumpValidator],
]) {
  describe(name, () => {
    const isValid = setUp();
    for (const [label, schema, values, expected] of CASES) {
      test(`${expected ? "accepts" : "rejects"} ${label}`, async () => {
        assert.equal(await isValid(schema, values), expected);
      });
    }
  });
}
