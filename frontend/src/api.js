/** Calls `/api/v1` and attaches a traceparent so a click lines up with the API span. */
import { tracer, traceparent } from "./telemetry";

const prefix = "/api/v1";

/**
 * JSON request helper. A 503 is returned instead of thrown so the ask page can
 * show the passages the API attached when the model is down.
 */
async function request(path, options = {}, spanName = "ui.request") {
  return tracer.startActiveSpan(spanName, async (span) => {
    try {
      const headers = new Headers(options.headers || {});
      const parent = traceparent();
      if (parent) {
        headers.set("traceparent", parent);
      }
      const response = await fetch(`${prefix}${path}`, { ...options, headers });
      const body = await response.json();
      span.setAttribute("http.status_code", response.status);
      span.setAttribute("success", Boolean(body.success));
      if (!response.ok && response.status !== 503) {
        const message = body.errors?.[0]?.msg || `Request failed (${response.status})`;
        const error = new Error(message);
        error.body = body;
        error.status = response.status;
        throw error;
      }
      return { status: response.status, body };
    } catch (error) {
      span.recordException(error);
      throw error;
    } finally {
      span.end();
    }
  });
}

export function getStatus() {
  return request("/status", {}, "ui.status");
}

export function listMakers(query = "") {
  return request(`/makers?q=${encodeURIComponent(query)}`, {}, "ui.list_makers");
}

export function listEquipmentModels(query = "") {
  return request(`/equipment-models?q=${encodeURIComponent(query)}`, {}, "ui.list_equipment_models");
}

export function listDocuments(offset = 1, limit = 5) {
  return request(`/documents?limit=${limit}&offset=${offset}`, {}, "ui.list_documents");
}

/** Read maker, model, and title from the file. Nothing is stored. */
export function describeDocument(file) {
  const data = new FormData();
  data.set("file", file);
  return request("/documents/identity", { method: "POST", body: data }, "ui.describe_document");
}

/** Upload the file. Empty names are omitted so the API fills them from the manual. */
export function uploadDocument(file, equipmentModel, title, maker) {
  const data = new FormData();
  data.set("file", file);
  const metadata = {};
  if (equipmentModel) {
    metadata.equipmentModel = equipmentModel;
  }
  if (title) {
    metadata.title = title;
  }
  if (maker) {
    metadata.maker = maker;
  }
  data.set("metadata", JSON.stringify(metadata));
  return request("/documents", { method: "POST", body: data }, "ui.upload");
}

export function getJob(jobId) {
  return request(`/jobs/${jobId}`, {}, "ui.poll_job");
}

export function listAliases() {
  return request("/aliases", {}, "ui.list_aliases");
}

export function createAlias(terms) {
  return request(
    "/aliases",
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ terms }) },
    "ui.create_alias",
  );
}

export function updateAlias(aliasId, terms) {
  return request(
    `/aliases/${aliasId}`,
    { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ terms }) },
    "ui.update_alias",
  );
}

export function deleteAlias(aliasId) {
  return request(`/aliases/${aliasId}`, { method: "DELETE" }, "ui.delete_alias");
}

/** Ask the manuals. equipmentModel, when set, limits retrieval to that model. */
export function askQuestion(question, equipmentModel) {
  const payload = { question, k: 5 };
  if (equipmentModel) {
    payload.equipmentModel = equipmentModel;
  }
  return request(
    "/answers",
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) },
    "ui.ask",
  );
}
