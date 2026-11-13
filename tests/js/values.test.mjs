// SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud / GA4GH Contributors
// SPDX-License-Identifier: Apache-2.0

// Validates input values against `inputs` of the examples (tests/data/)
// with JavaScript validators, offline, as tests/test_examples.py does in
// Python: with the semantics of JSON Schema Draft 2020-12 (see "Dialect and
// validation of values" in docs/specification/meta-schema.md, and
// docs/tools/javascript.md for the setup of each validator).

import assert from "node:assert/strict";
import { describe, test } from "node:test";

import {
  registerSchema,
  validate,
} from "@hyperjump/json-schema/draft-2020-12";

import {
  DRAFT_2020_12,
  EXAMPLES,
  PROFILE,
  SUITE,
  VOCABULARY_SCHEMAS,
  newAjv,
  readJson,
  setUpHyperjump,
} from "./helpers.mjs";

const TOOL = readJson(new URL("example_tool.schema.json", EXAMPLES));
const WORKFLOW = readJson(new URL("example_workflow.schema.json", EXAMPLES));
const INVALID = readJson(new URL("invalid/ui-widget-unknown.schema.json", SUITE));
const NOT_A_URI = readJson(new URL("invalid/ontology-not-uri.schema.json", SUITE));

// An IO schema without `$id` (which the profile allows), with a `format`;
// clients register it under a key of their choice.
const DATED = {
  $schema: PROFILE.$id,
  properties: {
    inputs: {
      type: "object",
      properties: { day: { type: "string", format: "date" } },
    },
  },
};
const DATED_KEY = "urn:example:dated";
const keyOf = (schema) => schema.$id ?? DATED_KEY;

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
  ["a date", DATED, { day: "2020-12-31" }, true],
  ["a value that fails its format", DATED, { day: "2020-13-45" }, false],
];

/** Return the URI of `inputs` of an IO schema with the given `$id`. */
const inputsUri = (id) => `${id}#/properties/inputs`;

/** Return Ajv with the profile added as a meta-schema. */
function ajvWithProfile() {
  const ajv = newAjv({ strict: false });
  ajv.addMetaSchema(PROFILE);
  return ajv;
}

/**
 * Return a function that validates values against `inputs` of an IO schema
 * with Ajv: the profile is added as a meta-schema, so that Ajv accepts IO
 * schemas that name it in `$schema`. Ajv's meta-schema check in `addSchema`
 * skips `format`, so it is not a conformance check; the examples are
 * checked against the profile in conformance.test.mjs.
 */
function ajvValidator() {
  const ajv = ajvWithProfile();
  ajv.addSchema(TOOL);
  ajv.addSchema(WORKFLOW);
  ajv.addSchema(DATED, DATED_KEY);
  return async (schema, values) => ajv.validate(inputsUri(keyOf(schema)), values);
}

/**
 * Return a function that validates values against `inputs` of an IO schema
 * with @hyperjump/json-schema: the IO schemas are registered as copies that
 * name the Draft 2020-12 dialect in `$schema` (see the test below for why).
 */
function hyperjumpValidator() {
  setUpHyperjump();
  for (const schema of [TOOL, WORKFLOW]) {
    registerSchema({ ...schema, $schema: DRAFT_2020_12 });
  }
  registerSchema({ ...DATED, $schema: DRAFT_2020_12 }, DATED_KEY);
  return async (schema, values) =>
    (await validate(inputsUri(keyOf(schema)), values)).valid;
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

// The setup above relies on these behaviours of the validators; if one of
// them changes, update docs/tools/javascript.md.
describe("behaviour of the validators", () => {
  test("Ajv checks an IO schema against the profile when it is added", () => {
    assert.throws(() => ajvWithProfile().addSchema(INVALID), /schema is invalid/);
  });

  // Ajv compiles a meta-schema with format assertion off, so the profile
  // added with addMetaSchema is no conformance check; the profile added
  // with addSchema is (as in conformance.test.mjs).
  test("Ajv doesn't assert formats of the profile added as a meta-schema", () => {
    assert.equal(ajvWithProfile().validate(PROFILE.$id, NOT_A_URI), true);
    const checker = newAjv({ strict: false });
    checker.addSchema(PROFILE);
    assert.equal(checker.validate(PROFILE.$id, NOT_A_URI), false);
  });

  // hyperjump removes `$schema` from a schema before it checks the schema
  // against its dialect, so the profile, which requires `$schema`, rejects
  // every IO schema.
  test("@hyperjump/json-schema rejects IO schemas as the profile's dialect", async () => {
    setUpHyperjump();
    for (const schema of VOCABULARY_SCHEMAS) registerSchema(schema);
    registerSchema(PROFILE);
    const id = `${WORKFLOW.$id}/unchanged`;
    registerSchema({ ...WORKFLOW, $id: id });
    await assert.rejects(validate(inputsUri(id), {}), /Invalid Schema/);
  });
});
