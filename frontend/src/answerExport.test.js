import { answerMarkdown, copyText, downloadMarkdown, markdownFilename } from "./answerExport";

const message = {
  question: "What is the minimum brake pad thickness?",
  text: "The minimum thickness is 4.2 mm.",
  confidence: "high",
  citations: [
    {
      title: "HX-200 brake service",
      page: 1,
      equipmentModel: "HX-200",
      excerpt: "minimum thickness is 4.2 mm",
    },
  ],
};

test("markdown includes the question, answer, confidence, and citations", () => {
  const text = answerMarkdown(message);
  expect(text).toContain("# What is the minimum brake pad thickness?");
  expect(text).toContain("The minimum thickness is 4.2 mm.");
  expect(text).toContain("Confidence: high");
  expect(text).toContain("### HX-200 brake service, page 1");
  expect(text).toContain("minimum thickness is 4.2 mm");
});

test("a refusal is marked and a missing question uses a fallback title", () => {
  const text = answerMarkdown({ text: "Not in the manuals.", refused: true });
  expect(text.startsWith("# Answer\n")).toBe(true);
  expect(text).toContain("Not answered from the manuals.");
  expect(text).not.toContain("## Citations");
});

test("long questions are trimmed on a word boundary", () => {
  const name = markdownFilename("What is the minimum brake pad thickness on the HX-200 right now");
  expect(name.endsWith(".md")).toBe(true);
  expect(name.length).toBeLessThan(52);
  expect(name.endsWith("-.md")).toBe(false);
  expect(markdownFilename("")).toBe("answer.md");
  expect(markdownFilename("!!!")).toBe("answer.md");
  expect(markdownFilename("a".repeat(60))).toBe(`${"a".repeat(48)}.md`);
});

test("copy uses the selection fallback", async () => {
  document.execCommand = () => true;
  await expect(copyText("4.2 mm")).resolves.toBeUndefined();
});

test("copy uses the clipboard when the selection fallback declines", async () => {
  document.execCommand = () => false;
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
  await copyText("4.2 mm");
  expect(writeText).toHaveBeenCalledWith("4.2 mm");
});

test("download saves the markdown under the question slug", () => {
  const created = [];
  const original = URL.createObjectURL;
  URL.createObjectURL = (blob) => {
    created.push(blob);
    return "blob:answer";
  };
  const clicks = [];
  const originalClick = HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click = function click() {
    clicks.push({ download: this.download, href: this.href });
  };
  try {
    downloadMarkdown(message);
  } finally {
    URL.createObjectURL = original;
    HTMLAnchorElement.prototype.click = originalClick;
  }
  expect(created[0].type).toContain("text/markdown");
  expect(clicks[0].download).toBe("what-is-the-minimum-brake-pad-thickness.md");
  expect(clicks[0].href).toBe("blob:answer");
});
