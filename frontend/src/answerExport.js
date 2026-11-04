/** Turn an answer and its citations into a Markdown file the technician can save. */
export function answerMarkdown(message) {
  const lines = [`# ${message.question || "Answer"}`, "", message.text, ""];
  if (message.confidence) {
    lines.push(`Confidence: ${message.confidence}`, "");
  }
  if (message.refused) {
    lines.push("Not answered from the manuals.", "");
  }
  if (message.citations?.length) {
    lines.push("## Citations", "");
    for (const citation of message.citations) {
      lines.push(
        `### ${citation.title}, page ${citation.page}`,
        "",
        citation.equipmentModel,
        "",
        citation.excerpt,
        "",
      );
    }
  }
  return lines.join("\n").trim() + "\n";
}

/** A short filename from the question, safe for a download. */
export function markdownFilename(question) {
  let slug = (question || "answer")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, "-")
    .replace(/^-|-$/g, "");
  if (slug.length > 48) {
    const cut = slug.slice(0, 48);
    const hyphen = cut.lastIndexOf("-");
    slug = (hyphen > 12 ? cut.slice(0, hyphen) : cut).replace(/-$/g, "");
  }
  return `${slug || "answer"}.md`;
}

/** Copy with a hidden textarea, then the clipboard API if the browser blocks that. */
export function copyText(text) {
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.left = "-9999px";
  document.body.appendChild(area);
  area.select();
  const copied = document.execCommand("copy");
  area.remove();
  if (!copied) {
    return navigator.clipboard.writeText(text);
  }
  return Promise.resolve();
}

/** Save the answer as a Markdown file named from the question. */
export function downloadMarkdown(message) {
  const blob = new Blob([answerMarkdown(message)], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = markdownFilename(message.question);
  link.click();
  URL.revokeObjectURL(url);
}
