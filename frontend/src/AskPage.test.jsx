import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { copyText } from "./answerExport";
import { AskPage } from "./AskPage";
import { askQuestion } from "./api";

vi.mock("./api", () => ({ askQuestion: vi.fn() }));
vi.mock("./answerExport", async () => {
  const actual = await vi.importActual("./answerExport");
  return {
    ...actual,
    copyText: vi.fn((text) => actual.copyText(text)),
  };
});

beforeEach(() => {
  askQuestion.mockReset();
});

const citation = {
  chunkId: "chunk-1",
  documentId: "doc-1",
  title: "HX-200 brake service",
  equipmentModel: "HX-200",
  page: 1,
  excerpt: "minimum thickness is 4.2 mm",
};

test("an answer can be copied and its manual downloaded", async () => {
  askQuestion.mockResolvedValue({
    status: 200,
    body: {
      data: {
        answer: "The minimum thickness is 4.2 mm.",
        answered: true,
        confidence: "high",
        citations: [citation],
      },
    },
  });
  document.execCommand = () => true;
  const user = userEvent.setup();
  render(<AskPage />);
  await user.type(screen.getByLabelText("Question"), "How thick is the pad?");
  await user.type(screen.getByLabelText("Limit to equipment model"), "HX-200");
  await user.click(screen.getByRole("button", { name: "Ask" }));

  expect(await screen.findByText("The minimum thickness is 4.2 mm.")).toBeInTheDocument();
  expect(askQuestion).toHaveBeenCalledWith("How thick is the pad?", "HX-200");
  await user.click(screen.getByRole("button", { name: "Copy" }));
  expect(screen.getByRole("button", { name: "Copied" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Download manual" })).toHaveAttribute(
    "href",
    "/api/v1/documents/doc-1/file",
  );
  expect(screen.getByRole("button", { name: "Download markdown" })).toBeInTheDocument();
});

test("a provider outage still shows the retrieved manual", async () => {
  askQuestion.mockResolvedValue({
    status: 503,
    body: {
      errors: [{ msg: "The model is unavailable." }],
      data: { citations: [citation] },
    },
  });
  const user = userEvent.setup();
  render(<AskPage />);
  await user.type(screen.getByLabelText("Question"), "pad thickness");
  await user.click(screen.getByRole("button", { name: "Ask" }));
  expect(await screen.findByText("The model is unavailable.")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Download manual" })).toHaveAttribute(
    "href",
    "/api/v1/documents/doc-1/file",
  );
});

test("an empty question is not sent", async () => {
  const user = userEvent.setup();
  render(<AskPage />);
  await user.click(screen.getByRole("button", { name: "Ask" }));
  expect(askQuestion).not.toHaveBeenCalled();
});

test("a failed copy tells the user", async () => {
  askQuestion.mockResolvedValue({
    status: 200,
    body: {
      data: {
        answer: "4.2 mm.",
        answered: false,
        citations: [],
      },
    },
  });
  copyText.mockRejectedValueOnce(new Error("denied"));
  const user = userEvent.setup();
  render(<AskPage />);
  await user.type(screen.getByLabelText("Question"), "pad thickness");
  await user.click(screen.getByRole("button", { name: "Ask" }));
  await screen.findByText("4.2 mm.");
  await user.click(screen.getByRole("button", { name: "Copy" }));
  expect(await screen.findByText("Could not copy the answer.")).toBeInTheDocument();
  expect(screen.getByText("Not answered from the manuals.")).toBeInTheDocument();
});

test("a failed question shows the error", async () => {
  askQuestion.mockRejectedValue(new Error("Request failed (500)"));
  const user = userEvent.setup();
  render(<AskPage />);
  await user.type(screen.getByLabelText("Question"), "pad thickness");
  await user.click(screen.getByRole("button", { name: "Ask" }));
  expect(await screen.findByText("Request failed (500)")).toBeInTheDocument();
});
