// SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud / GA4GH Contributors
// SPDX-License-Identifier: Apache-2.0

// The page of the host (form_host.py): fetches the schema, renders the form,
// sends the values to the host and shows the `workflow_params` or the
// errors. A proof of concept (see docs/adoption/form.md).

import "./io-schema-form.js";

const form = document.querySelector("io-schema-form");
const result = document.querySelector("#params");

const response = await fetch("api/schema");
const schema = await response.json();
document.querySelector("#title").textContent = schema.title ?? "IO schema";
document.querySelector("#description").textContent = schema.description ?? "";
form.schema = schema;

form.addEventListener("io-schema-form-submit", async (event) => {
  const answer = await fetch("api/params", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(event.detail.values),
  });
  const body = await answer.json();
  form.showErrors(body.errors ?? []);
  result.textContent = body.workflow_params
    ? JSON.stringify(body.workflow_params, null, 2)
    : "(none: the values have errors)";
});
