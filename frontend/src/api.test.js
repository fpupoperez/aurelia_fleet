import {
  askQuestion,
  createAlias,
  deleteAlias,
  getJob,
  getStatus,
  listAliases,
  listDocuments,
  listEquipmentModels,
  listMakers,
  updateAlias,
  describeDocument,
  uploadDocument,
} from "./api";

const span = {
  setAttribute() {},
  recordException() {},
  end() {},
};

vi.mock("./telemetry", () => ({
  tracer: {
    startActiveSpan: (_name, fn) => fn(span),
  },
  traceparent: () => "00-aa-bb-01",
}));

function jsonResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

test("a successful call returns the envelope and sends the trace parent", async () => {
  fetch.mockResolvedValue(jsonResponse(200, { success: true, data: { status: "ok" } }));
  const result = await getStatus();
  expect(result.status).toBe(200);
  expect(result.body.data.status).toBe("ok");
  const [, options] = fetch.mock.calls[0];
  expect(options.headers.get("traceparent")).toBe("00-aa-bb-01");
});

test("a provider outage is returned instead of thrown", async () => {
  fetch.mockResolvedValue(jsonResponse(503, { success: false, errors: [{ msg: "down" }], data: { citations: [] } }));
  const result = await askQuestion("thickness", "");
  expect(result.status).toBe(503);
  expect(result.body.errors[0].msg).toBe("down");
});

test("an error uses the envelope message", async () => {
  fetch.mockResolvedValue(jsonResponse(400, { success: false, errors: [{ msg: "bad model" }] }));
  await expect(askQuestion("thickness", "HX-200")).rejects.toThrow("bad model");
});

test("library and alias calls use their routes", async () => {
  fetch.mockResolvedValue(jsonResponse(200, { success: true, data: { objects: [] } }));
  await listMakers("au");
  await listEquipmentModels("hx");
  await listDocuments(2, 5);
  await listAliases();
  await createAlias(["gnss", "gps"]);
  await updateAlias("a1", ["gps"]);
  await deleteAlias("a1");
  await getJob("job-1");
  const paths = fetch.mock.calls.map(([url]) => url);
  expect(paths).toEqual([
    "/api/v1/makers?q=au",
    "/api/v1/equipment-models?q=hx",
    "/api/v1/documents?limit=5&offset=2",
    "/api/v1/aliases",
    "/api/v1/aliases",
    "/api/v1/aliases/a1",
    "/api/v1/aliases/a1",
    "/api/v1/jobs/job-1",
  ]);
});

test("upload omits an empty maker", async () => {
  fetch.mockResolvedValue(jsonResponse(201, { success: true, data: {} }));
  const file = new File(["pad"], "brakes.md", { type: "text/markdown" });
  await uploadDocument(file, "HX-200", "Brakes", "");
  expect(JSON.parse(fetch.mock.calls[0][1].body.get("metadata")).maker).toBeUndefined();
});

test("a response without an error message still throws", async () => {
  fetch.mockResolvedValue(jsonResponse(500, { success: false }));
  await expect(getStatus()).rejects.toThrow("Request failed (500)");
});

test("describe sends the file and does not store metadata", async () => {
  fetch.mockResolvedValue(jsonResponse(200, { success: true, data: { equipmentModel: "Pro5S" } }));
  const file = new File(["%PDF"], "pro5s.pdf", { type: "application/pdf" });
  await describeDocument(file);
  const body = fetch.mock.calls[0][1].body;
  expect(fetch.mock.calls[0][0]).toBe("/api/v1/documents/identity");
  expect(body.get("file")).toBe(file);
  expect(body.get("metadata")).toBeNull();
});

test("upload sends the file and the maker when one is set", async () => {
  fetch.mockResolvedValue(jsonResponse(201, { success: true, data: { jobId: "j1" } }));
  const file = new File(["pad"], "brakes.md", { type: "text/markdown" });
  await uploadDocument(file, "HX-200", "Brakes", "Aurelia");
  const body = fetch.mock.calls[0][1].body;
  expect(body.get("file")).toBe(file);
  expect(JSON.parse(body.get("metadata"))).toEqual({
    equipmentModel: "HX-200",
    title: "Brakes",
    maker: "Aurelia",
  });
});
