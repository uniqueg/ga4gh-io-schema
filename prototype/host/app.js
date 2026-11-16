// SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud / GA4GH Contributors
// SPDX-License-Identifier: Apache-2.0

// The page of the host (form_host.py): fetches the schema, renders the form,
// sends the values to the host and shows the WES run request or the errors;
// with a WES configured, it can also submit the run. A proof of concept (see
// docs/adoption/form.md).

import "./io-schema-form.js";

const form = document.querySelector("io-schema-form");
const result = document.querySelector("#request");
const submit = document.querySelector("#submit-run");
const run = document.querySelector("#run");
let values = null;

const [schema, config] = await Promise.all(
  ["api/schema", "api/config"].map(async (path) => (await fetch(path)).json()),
);
document.querySelector("#title").textContent = schema.title ?? "IO schema";
document.querySelector("#description").textContent = schema.description ?? "";
document.querySelector("#wes").textContent = config.wes
  ? "A WES is configured: a valid run request can be sent there."
  : "No WES is configured: the run request is shown, not sent.";
form.schema = schema;

async function post(path, body) {
  const answer = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return answer.json();
}

form.addEventListener("io-schema-form-submit", async (event) => {
  const body = await post("api/params", event.detail.values);
  form.showErrors(body.errors ?? []);
  values = body.run_request ? event.detail.values : null;
  result.textContent = body.run_request
    ? JSON.stringify(body.run_request, null, 2)
    : "(none: the values have errors)";
  submit.hidden = !(config.wes && values);
  run.textContent = "";
});

submit.addEventListener("click", async () => {
  submit.disabled = true;
  try {
    const body = await post("api/runs", values);
    run.textContent = body.run_id
      ? `Run ${body.run_id}: ${body.state ?? "state unknown"}`
      : (body.errors ?? []).map((error) => error.message).join("\n");
  } finally {
    submit.disabled = false;
  }
});
