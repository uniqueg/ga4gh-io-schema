// SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
// SPDX-License-Identifier: Apache-2.0

// The page of the host (form_host.py): lists the workflows of the TRS, if
// any, fetches the schema of the picked one (the query `tool`, `version` and
// `type` of the page), renders the form, sends the values to the host and
// shows the WES run request or the errors; with a WES configured, it can also
// submit the run. A proof of concept (see docs/adoption/form.md).

import "./io-schema-form.js";

const form = document.querySelector("io-schema-form");
const result = document.querySelector("#request");
const submit = document.querySelector("#submit-run");
const run = document.querySelector("#run");
const status = document.querySelector("#wes");
const picker = document.querySelector("#workflow");
// The picked workflow, passed on to the host with every request
const pick = location.search;
let values = null;

let schema, config;
try {
  [schema, config] = await Promise.all(
    [`api/schema${pick}`, "api/config"].map(async (path) => (await fetch(path)).json()),
  );
} catch (error) {
  status.textContent = `The host failed: ${error}`;
  throw error;
}
status.textContent = config.wes
  ? "A WES is configured: a valid run request can be sent there."
  : "No WES is configured: the run request is shown, not sent.";

// The workflows of the TRS; picking one loads the page for it.
if (config.workflows) {
  picker.parentElement.hidden = false;
  const none = new Option(config.trs_error ?? "(pick a workflow)", "");
  picker.append(none);
  for (const workflow of config.workflows) {
    const query = new URLSearchParams({
      tool: workflow.tool_id,
      version: workflow.version_id,
      type: workflow.descriptor_type,
    });
    const label = `${workflow.name} ${workflow.version_id} (${workflow.descriptor_type})`;
    const option = new Option(label, `?${query}`);
    option.selected = option.value === pick;
    picker.append(option);
  }
  picker.addEventListener("change", () => {
    location.search = picker.value;
  });
}

if (schema.errors) {
  // No schema: none picked, or the picked one can't be loaded
  document.querySelector("#description").textContent = schema.errors
    .map((error) => error.message)
    .join("\n");
  form.hidden = true;
} else {
  document.querySelector("#title").textContent = schema.title ?? "IO schema";
  document.querySelector("#description").textContent = schema.description ?? "";
  form.schema = schema;
}

// Posts JSON to the host; a failure (network, or an answer that isn't JSON)
// becomes an error of the request as a whole.
async function post(path, body) {
  try {
    const answer = await fetch(`${path}${pick}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return await answer.json();
  } catch (error) {
    return { errors: [{ pointer: "", message: `The host failed: ${error}` }] };
  }
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
