# JavaScript validators

The [meta-schema](../specification/meta-schema.md) is plain JSON Schema
Draft 2020-12, so JavaScript clients (e.g., form renderers in a browser) can
check IO schemas against it with a JavaScript validator instead of the
[Python validator](validator.md). This page describes how to set up the
validators that the repository tests, and their results on the
[conformance suite](../specification/conformance.md#conformance-suite).

## Results

`tests/js/` runs every case of the conformance suite and the examples of
`tests/data/` through each validator, offline, with the setup described
below (see [Development](../development.md#javascript-tests-nodejs)); CI
runs it on every pull request. The versions are those pinned in
`tests/js/package.json`. The setup functions of
`tests/js/conformance.test.mjs` are a complete, runnable version of the
snippets below, including how the schemas are read from `schemas/`.

| Validator | Options | Valid documents accepted | Invalid documents rejected |
| ----- | ----- | ----- | ----- |
| [Ajv](https://ajv.js.org/) 8.20.0 (`ajv/dist/2020`) with [ajv-formats](https://github.com/ajv-validator/ajv-formats) 3.0.1 | `strict: false` | All | All |
| Ajv 8.20.0 with ajv-formats 3.0.1 | `strict: false, allErrors: true` | All | All |
| Ajv 8.20.0 with ajv-formats 3.0.1 | `strict: true, strictTypes: false, strictRequired: false` | All | All |
| [@hyperjump/json-schema](https://github.com/hyperjump-io/json-schema) 1.18.0 | format assertion on | All | All |

These are the results of the Python validator, too. Without format
assertion (Ajv without ajv-formats, or hyperjump with its default), both
accept `ontology-not-uri`, whose `x-ga4gh-ontology` isn't a URI: a
[validator](../specification/conformance.md#validator) must check the
`format` keywords of the meta-schema.

The validators differ in the formats of the Draft 2020-12 meta-schema,
which the profile's meta-schema applies to every schema, and which no case
of the suite tests yet:

- Ajv doesn't check them, even with ajv-formats, because it turns format
  validation off for its built-in meta-schemas. It accepts, for example, a
  nested `{"$ref": "#/$defs/a b"}` (not a `uri-reference`) or
  `{"$schema": "not a uri"}`, which the Python validator and hyperjump
  reject.
- hyperjump also checks the `regex` format of `pattern` with the regular
  expressions of JavaScript (ECMA-262), e.g., it rejects `"pattern": "("`;
  the Python validator and Ajv don't.

Validators that report all errors (e.g., Ajv with `allErrors: true`) report
a problem in a nested schema more than once: both the Draft 2020-12
meta-schema and the rules of the profile check every subschema. The valid
`x-ga4gh-*` keywords of the enclosing schemas are not reported: the check
of unevaluated keywords sees only the vocabularies, which a failed nested
schema doesn't affect.

The meta-schema applies the rules for nested schemas with explicit `$ref`s,
not with `$dynamicAnchor`, which Ajv supports only at the root of a schema:
with `$dynamicAnchor`, Ajv would skip every rule for nested schemas (e.g.,
unknown widgets, bad file references) without an error (see
[Structure of the meta-schema](../specification/meta-schema.md#structure-of-the-meta-schema)).

Other validators aren't tested. A validator conforms if it accepts every
valid and rejects every invalid document of the suite, with the setup
requirements of [Validator](../specification/conformance.md#validator):
local copies of the schemas, no retrieval over the network, and format
assertion.

## Ajv

Use the Draft 2020-12 build of Ajv, add ajv-formats, and add the
meta-schema and every vocabulary file of `schemas/` from local copies, so
that Ajv resolves the `$ref`s between them without fetching:

```js
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

const ajv = new Ajv2020({ strict: false });
addFormats(ajv);
for (const schema of vocabularies) ajv.addSchema(schema); // schemas/vocabularies/*.schema.json
ajv.addSchema(profile); // schemas/ga4gh-io-profile.schema.json
const validateIoSchema = ajv.getSchema(profile.$id);

if (!validateIoSchema(ioSchema)) console.log(validateIoSchema.errors);
```

Ajv's [strict mode](https://ajv.js.org/strict-mode.html) can stay on,
except for two of its checks, which the meta-schema can't meet without
changing what it accepts:

- `strictTypes: false`: the keywords of every schema
  (`$defs/node/$defs/keywords`) use `properties` and `patternProperties`
  without `"type": "object"`, because they also apply to boolean schemas
  (`true`, `false`), which `"type": "object"` would reject.
- `strictRequired: false`: the vocabulary of `x-ga4gh-workflow` requires
  `entry_point` in the `then` of a condition (for WDL), and defines it in
  the enclosing schema, not in `then`.

Ajv compiles schemas into JavaScript functions with `new Function`; in a
browser, the page's Content Security Policy must then allow `'unsafe-eval'`
(see [Ajv's security notes](https://ajv.js.org/security.html)).

## @hyperjump/json-schema

Turn off retrieval over HTTP(S), which hyperjump does by default for
unknown `$ref`s, turn on format assertion, and register the meta-schema and
every vocabulary file from local copies:

```js
import { removeUriSchemePlugin } from "@hyperjump/browser";
import {
  registerSchema,
  setShouldValidateFormat,
  validate,
} from "@hyperjump/json-schema/draft-2020-12";
import "@hyperjump/json-schema/formats";

removeUriSchemePlugin("http");
removeUriSchemePlugin("https");
setShouldValidateFormat(true);
for (const schema of vocabularies) registerSchema(schema);
registerSchema(profile);

const output = await validate(profile.$id, ioSchema);
if (!output.valid) console.log(output.errors);
```

hyperjump doesn't compile schemas with `new Function`, so it needs no
`'unsafe-eval'`. Its errors name the keyword (as a URI) and the location in
the document, without a message text.
