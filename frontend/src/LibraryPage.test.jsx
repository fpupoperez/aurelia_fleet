import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LibraryPage } from "./LibraryPage";
import { describeDocument, getJob, listDocuments, uploadDocument } from "./api";

vi.mock("./api", () => ({
  listDocuments: vi.fn(),
  listEquipmentModels: vi.fn().mockResolvedValue({ body: { data: { objects: [] } } }),
  listMakers: vi.fn().mockResolvedValue({ body: { data: { objects: [] } } }),
  describeDocument: vi.fn().mockResolvedValue({ body: { data: { equipmentModel: "", maker: "", title: "" } } }),
  uploadDocument: vi.fn(),
  getJob: vi.fn(),
}));

const manual = {
  documentId: "doc-9",
  title: "HX-200 brake service",
  equipmentModel: "HX-200",
  maker: "Aurelia",
  filename: "brakes.pdf",
  mediaType: "application/pdf",
  language: "en",
  chunkCount: 2,
  pageCount: 1,
  status: "completed",
  createdAt: "2026-11-04T13:00:00Z",
};

test("the open manual links to the original file", async () => {
  listDocuments.mockResolvedValue({ body: { data: { count: 1, objects: [manual] } } });
  const user = userEvent.setup();
  render(<LibraryPage />);
  await user.click(await screen.findByRole("button", { name: /HX-200 brake service/ }));
  const link = screen.getByRole("link", { name: "Download brakes.pdf" });
  expect(link).toHaveAttribute("href", "/api/v1/documents/doc-9/file");
  expect(link).toHaveAttribute("download", "brakes.pdf");
  expect(screen.getByText("PDF")).toBeInTheDocument();
  expect(screen.getByText("en")).toBeInTheDocument();
});

test("markdown and text manuals name their file type", async () => {
  listDocuments.mockResolvedValue({
    body: {
      data: {
        count: 2,
        objects: [
          { ...manual, documentId: "md", filename: "notes.md", mediaType: "text/markdown", language: null, chunkCount: 0 },
          { ...manual, documentId: "txt", title: "Antenna note", filename: "antenna.txt", mediaType: "text/plain", maker: "" },
        ],
      },
    },
  });
  const user = userEvent.setup();
  render(<LibraryPage />);
  await user.click(await screen.findByRole("button", { name: /HX-200 brake service/ }));
  expect(screen.getByText("Markdown")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: /Antenna note/ }));
  expect(screen.getByText("Text")).toBeInTheDocument();
});

test("upload requires a file", async () => {
  listDocuments.mockResolvedValue({ body: { data: { count: 0, objects: [] } } });
  const user = userEvent.setup();
  render(<LibraryPage />);
  await user.click(screen.getByRole("button", { name: "Upload manual" }));
  expect(await screen.findByText("Choose a file.")).toBeInTheDocument();
});

test("choosing a file fills the maker and model from the manual", async () => {
  listDocuments.mockResolvedValue({ body: { data: { count: 0, objects: [] } } });
  describeDocument.mockResolvedValue({
    body: { data: { equipmentModel: "Pro5S", maker: "Ruptela", title: "Pro5S datasheet" } },
  });
  uploadDocument.mockResolvedValue({ body: { data: { jobId: "job-1" } } });
  getJob.mockResolvedValue({ body: { data: { jobId: "job-1", status: "completed", title: "Pro5S datasheet" } } });
  const user = userEvent.setup();
  render(<LibraryPage />);
  await user.upload(screen.getByLabelText("File"), new File(["%PDF"], "pro5s.pdf", { type: "application/pdf" }));
  expect(await screen.findByDisplayValue("Pro5S")).toBeInTheDocument();
  expect(screen.getByLabelText("Maker")).toHaveValue("Ruptela");
  expect(screen.getByLabelText("Title")).toHaveValue("Pro5S datasheet");
  await user.click(screen.getByRole("button", { name: "Upload manual" }));
  expect(uploadDocument).toHaveBeenCalledWith(expect.any(File), "Pro5S", "Pro5S datasheet", "Ruptela");
});

test("a completed upload returns to the first page", async () => {
  listDocuments.mockResolvedValue({ body: { data: { count: 0, objects: [] } } });
  uploadDocument.mockResolvedValue({ body: { data: { jobId: "job-1" } } });
  getJob.mockResolvedValue({ body: { data: { jobId: "job-1", status: "completed", title: "Note" } } });
  const user = userEvent.setup();
  render(<LibraryPage />);
  await screen.findByText(/No manuals yet/);
  await user.upload(screen.getByLabelText("File"), new File(["torque"], "note.txt", { type: "text/plain" }));
  await user.type(screen.getByLabelText("Equipment model"), "HX-200");
  await user.type(screen.getByLabelText("Title"), "Note");
  await user.click(screen.getByRole("button", { name: "Upload manual" }));
  expect(await screen.findByText(/Note: completed/)).toBeInTheDocument();
  expect(uploadDocument).toHaveBeenCalled();
});

test("an empty library explains how to add a manual", async () => {
  listDocuments.mockResolvedValue({ body: { data: { count: 0, objects: [] } } });
  render(<LibraryPage />);
  expect(await screen.findByText(/No manuals yet/)).toBeInTheDocument();
});
