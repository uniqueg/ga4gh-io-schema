// SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud / GA4GH Contributors
// SPDX-License-Identifier: Apache-2.0

// `<io-schema-form>`: renders the inputs of an IO schema as a form. Set
// `schema` to the IO schema; on submit, the element sends
// `io-schema-form-submit` with the values in `detail.values`. Show errors
// with `showErrors()`. Text from the schema is set as text, never as HTML.
// A proof of concept (see docs/adoption/form.md).

import {
  describeFields,
  fieldForError,
  formatValue,
  parseValue,
  pointerOf,
  setAt,
} from "./form.js";

let nextId = 0;

/**
 * Create an element with attributes and text.
 *
 * @param {string} tag The tag name.
 * @param {object} [attributes] Attributes to set.
 * @param {string} [text] Text content.
 * @returns {HTMLElement} The element.
 */
function element(tag, attributes = {}, text = undefined) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, value);
  if (text !== undefined) node.textContent = text;
  return node;
}

class IoSchemaForm extends HTMLElement {
  #fields = [];
  #controls = new Map();

  /** @param {object} schema The IO schema, validated by the host. */
  set schema(schema) {
    this.#fields = describeFields(schema, schema.properties.inputs);
    this.#controls.clear();
    const form = element("form", { novalidate: "" });
    form.append(...this.#renderGroup(this.#fields));
    form.append(element("p", { class: "form-error", role: "alert" }));
    form.append(element("button", { type: "submit" }, "Submit"));
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      this.dispatchEvent(
        new CustomEvent("io-schema-form-submit", { detail: { values: this.values } }),
      );
    });
    this.replaceChildren(form);
  }

  /** @returns {object} The values that the user has set. */
  get values() {
    const values = {};
    for (const [field, read] of this.#controls) setAt(values, field.path, parseValue(field, read()));
    return values;
  }

  /**
   * Show errors next to their inputs, or above the button if no input
   * matches; clears the errors shown before.
   *
   * @param {Array<{pointer: string, message: string}>} errors The errors.
   */
  showErrors(errors) {
    for (const node of this.querySelectorAll(".error")) node.textContent = "";
    const general = this.querySelector(".form-error");
    general.textContent = "";
    for (const { pointer, message } of errors) {
      const field = fieldForError(this.#fields, pointer);
      const target = field ? this.querySelector(`#${field.id}-error`) : general;
      // The location is named unless it is the field's own
      const text = field && pointerOf(field.path) === pointer ? message : `${pointer || "/"}: ${message}`;
      target.textContent = [target.textContent, text]
        .filter(Boolean)
        .join("\n");
      // A hidden input with an error is shown
      const details = target.closest("details");
      if (details) details.open = true;
    }
  }

  /**
   * Render a group of fields: the shown ones, then the hidden ones under
   * "Advanced".
   *
   * @param {Array<object>} fields The fields.
   * @returns {Array<HTMLElement>} The elements.
   */
  #renderGroup(fields) {
    const shown = fields.filter((field) => !field.hidden).map((field) => this.#renderField(field));
    const hidden = fields.filter((field) => field.hidden).map((field) => this.#renderField(field));
    if (!hidden.length) return shown;
    const details = element("details");
    details.append(element("summary", {}, "Advanced"), ...hidden);
    return [...shown, details];
  }

  /**
   * Render one field: its label, control, description and error.
   *
   * @param {object} field The field.
   * @returns {HTMLElement} The element.
   */
  #renderField(field) {
    nextId += 1;
    field.id = `io-field-${nextId}`;
    const wrapper = element(field.control === "object" ? "fieldset" : "div", { class: "field" });
    const label = `${field.label}${field.required ? " *" : ""}`;
    if (field.control === "object") {
      wrapper.append(element("legend", {}, label));
      if (field.description) wrapper.append(element("p", { class: "description" }, field.description));
      wrapper.append(element("p", { id: `${field.id}-error`, class: "error" }));
      wrapper.append(...this.#renderGroup(field.children));
      return wrapper;
    }
    wrapper.append(element("label", { for: field.id }, label));
    wrapper.append(this.#renderControl(field));
    if (field.description) wrapper.append(element("p", { class: "description" }, field.description));
    wrapper.append(element("p", { id: `${field.id}-error`, class: "error", "aria-live": "polite" }));
    return wrapper;
  }

  /**
   * Render the control of a field, prefilled with its default, and
   * remember how to read it.
   *
   * @param {object} field The field.
   * @returns {HTMLElement} The control.
   */
  #renderControl(field) {
    const { control, schema } = field;
    const initial = formatValue(field, field.defaultValue);
    const attributes = { id: field.id, name: field.name, "aria-describedby": `${field.id}-error` };
    let node;
    if (control === "select" || control === "boolean-select" || control === "multiselect") {
      node = element("select", control === "multiselect" ? { ...attributes, multiple: "" } : attributes);
      const options =
        control === "boolean-select" ? [true, false] : control === "select" ? schema.enum : schema.items.enum;
      if (control !== "multiselect") node.append(element("option", { value: "" }, ""));
      options.forEach((option, index) => {
        const value = control === "boolean-select" ? String(option) : String(index);
        const item = element("option", { value }, JSON.stringify(option).replace(/^"|"$/g, ""));
        item.selected = [initial].flat().includes(value);
        node.append(item);
      });
      const read =
        control === "multiselect" ? () => [...node.selectedOptions].map((option) => option.value) : () => node.value;
      this.#controls.set(field, read);
      return node;
    }
    if (control === "radio") {
      node = element("div", { id: field.id, role: "radiogroup" });
      schema.enum.forEach((option, index) => {
        const input = element("input", { type: "radio", name: field.id, value: String(index) });
        input.checked = initial === String(index);
        const label = element("label");
        label.append(input, ` ${JSON.stringify(option).replace(/^"|"$/g, "")}`);
        node.append(label);
      });
      this.#controls.set(field, () => node.querySelector("input:checked")?.value ?? "");
      return node;
    }
    if (control === "textarea" || control === "lines" || control === "json") {
      node = element("textarea", { ...attributes, rows: "3" });
      if (control === "lines") node.placeholder = "One value per line";
      if (control === "json") node.placeholder = "JSON";
    } else if (control === "checkbox") {
      node = element("input", { ...attributes, type: "checkbox" });
      node.checked = initial;
      this.#controls.set(field, () => node.checked);
      return node;
    } else {
      const type = { number: "number", slider: "number", date: "date", color: "color" }[control] ?? "text";
      node = element("input", { ...attributes, type });
      for (const bound of ["minimum", "maximum"]) {
        if (typeof schema[bound] === "number") node.setAttribute(bound.slice(0, 3), String(schema[bound]));
      }
      if (control === "file") {
        const schemes = schema["x-ga4gh-file"]?.schemes;
        node.placeholder = schemes ? `${schemes.join(", ")} URL` : "URL or path";
      }
    }
    node.value = initial;
    if (control === "slider") {
      // A number field next to the slider shows its value, and also takes
      // values that the slider can't produce, so that validation sees them
      const range = element("input", { type: "range", "aria-hidden": "true", tabindex: "-1" });
      for (const bound of ["min", "max"]) range.setAttribute(bound, node.getAttribute(bound));
      range.value = initial;
      range.addEventListener("input", () => {
        node.value = range.value;
      });
      node.addEventListener("input", () => {
        range.value = node.value;
      });
      this.#controls.set(field, () => node.value);
      const wrapper = element("span", { class: "slider" });
      wrapper.append(range, " ", node);
      return wrapper;
    }
    this.#controls.set(field, () => node.value);
    return node;
  }
}

customElements.define("io-schema-form", IoSchemaForm);
