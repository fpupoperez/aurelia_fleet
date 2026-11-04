/** Question page. Copy and Markdown download use the text already on screen. */
import { useState } from "react";
import { askQuestion } from "./api";
import { copyText, downloadMarkdown } from "./answerExport";

export function AskPage() {
  const [question, setQuestion] = useState("");
  const [filterModel, setFilterModel] = useState("");
  const [asking, setAsking] = useState(false);
  const [chatError, setChatError] = useState("");
  const [messages, setMessages] = useState([]);
  const [copiedIndex, setCopiedIndex] = useState(null);

  async function onAsk(event) {
    event.preventDefault();
    const text = question.trim();
    if (!text) {
      return;
    }
    setAsking(true);
    setChatError("");
    setMessages((current) => [...current, { role: "user", text }]);
    setQuestion("");
    try {
      const { status, body } = await askQuestion(text, filterModel.trim());
      if (status === 503) {
        setMessages((current) => [
          ...current,
          {
            role: "assistant",
            question: text,
            text: body.errors?.[0]?.msg || "The model is unavailable.",
            citations: body.data?.citations || [],
            refused: true,
          },
        ]);
        return;
      }
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          question: text,
          text: body.data.answer,
          citations: body.data.citations || [],
          refused: body.data.answered === false,
          confidence: body.data.confidence,
        },
      ]);
    } catch (error) {
      setChatError(error.message);
    } finally {
      setAsking(false);
    }
  }

  return (
    <>
      <header className="mast">
        <p className="eyebrow">Aurelia Fleet Services</p>
        <h1>Ask a technical question</h1>
        <p className="lede">
          Ask in plain language. Answers cite the page they came from, or they say the manuals do not contain the fact.
        </p>
      </header>
      <section className="panel chat ask-wrap">
        <div className="thread">
          {messages.length === 0 ? (
            <p className="muted">Ask about a procedure, a torque, a limit, or which devices support a feature.</p>
          ) : null}
          {messages.map((message, index) => (
            <article key={index} className={message.role}>
              <p>{message.text}</p>
              {message.refused ? <p className="flag">Not answered from the manuals.</p> : null}
              {message.confidence ? <p className="flag">Confidence: {message.confidence}</p> : null}
              {message.role === "assistant" ? (
                <div className="answer-actions">
                  <button
                    type="button"
                    className="quiet"
                    onClick={async () => {
                      try {
                        await copyText(message.text);
                        setCopiedIndex(index);
                        setChatError("");
                      } catch {
                        setChatError("Could not copy the answer.");
                      }
                    }}
                  >
                    {copiedIndex === index ? "Copied" : "Copy"}
                  </button>
                  <button type="button" className="quiet" onClick={() => downloadMarkdown(message)}>
                    Download markdown
                  </button>
                </div>
              ) : null}
              {message.citations?.length ? (
                <details>
                  <summary>
                    {message.citations.length} citation{message.citations.length === 1 ? "" : "s"}
                  </summary>
                  <ul className="citations">
                    {message.citations.map((citation) => (
                      <li key={citation.chunkId}>
                        <strong>
                          {citation.title}, page {citation.page}
                        </strong>
                        <span>{citation.equipmentModel}</span>
                        <blockquote>{citation.excerpt}</blockquote>
                        <a className="citation-download" href={`/api/v1/documents/${citation.documentId}/file`}>
                          Download manual
                        </a>
                      </li>
                    ))}
                  </ul>
                </details>
              ) : null}
            </article>
          ))}
          {asking ? <p className="muted">Looking through the manuals…</p> : null}
          {chatError ? <p className="error">{chatError}</p> : null}
        </div>
        <form className="ask" onSubmit={onAsk}>
          <label>
            Limit to equipment model
            <input
              value={filterModel}
              onChange={(event) => setFilterModel(event.target.value)}
              placeholder="Optional, for example HX-200"
            />
          </label>
          <label>
            Question
            <textarea
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              rows={3}
              placeholder="Which devices support CAN bus?"
            />
          </label>
          <button type="submit" disabled={asking}>
            Ask
          </button>
        </form>
      </section>
    </>
  );
}
