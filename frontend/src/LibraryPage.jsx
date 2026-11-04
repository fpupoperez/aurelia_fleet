/** Library page. Choosing a file fills maker, model, and title; the fields stay editable. */
import { useEffect, useRef, useState } from "react";
import { describeDocument, getJob, listDocuments, listEquipmentModels, listMakers, uploadDocument } from "./api";

const PAGE_SIZE = 5;

export function LibraryPage() {
  const [documents, setDocuments] = useState([]);
  const [page, setPage] = useState(1);
  const [count, setCount] = useState(0);
  const [libraryError, setLibraryError] = useState("");
  const [loadingLibrary, setLoadingLibrary] = useState(true);
  const [file, setFile] = useState(null);
  const [reading, setReading] = useState(false);
  const [equipmentModel, setEquipmentModel] = useState("");
  const [maker, setMaker] = useState("");
  const [title, setTitle] = useState("");
  const [uploadError, setUploadError] = useState("");
  const [job, setJob] = useState(null);
  const [formKey, setFormKey] = useState(0);
  const [openId, setOpenId] = useState(null);

  async function refresh(nextPage = page) {
    setLoadingLibrary(true);
    try {
      const { body } = await listDocuments(nextPage, PAGE_SIZE);
      const total = body.data?.count || 0;
      const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
      const safePage = Math.min(nextPage, pages);
      if (safePage !== nextPage) {
        setPage(safePage);
        return;
      }
      setDocuments(body.data?.objects || []);
      setCount(total);
      setPage(safePage);
      setLibraryError("");
    } catch (error) {
      setLibraryError(error.message);
    } finally {
      setLoadingLibrary(false);
    }
  }

  useEffect(() => {
    refresh(page);
  }, [page]);

  useEffect(() => {
    if (!job || job.status === "completed" || job.status === "failed") {
      return undefined;
    }
    const timer = setInterval(async () => {
      try {
        const { body } = await getJob(job.jobId);
        setJob(body.data);
        if (body.data.status === "completed" || body.data.status === "failed") {
          setPage(1);
          refresh(1);
        }
      } catch (error) {
        setUploadError(error.message);
      }
    }, 1500);
    return () => clearInterval(timer);
  }, [job]);

  async function onUpload(event) {
    event.preventDefault();
    setUploadError("");
    if (!file) {
      setUploadError("Choose a file.");
      return;
    }
    try {
      const { body } = await uploadDocument(file, equipmentModel.trim(), title.trim(), maker.trim());
      const status = await getJob(body.data.jobId);
      setJob(status.body.data);
      setFile(null);
      setEquipmentModel("");
      setMaker("");
      setTitle("");
      setFormKey((current) => current + 1);
      if (status.body.data.status === "completed") {
        setPage(1);
        refresh(1);
      }
    } catch (error) {
      setUploadError(error.message);
    }
  }

  /** Fill the form from the file. The user can still type over any field before upload. */
  async function onFile(next) {
    setFile(next);
    setUploadError("");
    if (!next) {
      return;
    }
    setReading(true);
    try {
      const { body } = await describeDocument(next);
      const found = body.data || {};
      setEquipmentModel(found.equipmentModel || "");
      setMaker(found.maker || "");
      setTitle(found.title || "");
    } catch (error) {
      setUploadError(error.message);
    } finally {
      setReading(false);
    }
  }

  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));
  const from = count === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const to = Math.min(page * PAGE_SIZE, count);

  return (
    <>
      <header className="mast">
        <p className="eyebrow">Aurelia Fleet Services</p>
        <h1>Library</h1>
        <p className="lede">Upload a service manual and wait until it is indexed. The list is paged five manuals at a time.</p>
      </header>
      <div className="library-layout">
        <section className="panel">
          <h2>Upload</h2>
          <form key={formKey} className="stack" onSubmit={onUpload}>
            <label>
              File
              <input
                type="file"
                accept=".pdf,.md,.markdown,.txt,application/pdf,text/plain,text/markdown"
                onChange={(event) => onFile(event.target.files?.[0] || null)}
              />
            </label>
            <p className="muted">Maker and model are filled from the file. Type them when the manual does not name them.</p>
            {reading ? <p className="muted">Reading the manual…</p> : null}
            <SuggestField
              label="Equipment model"
              placeholder="HX-200"
              value={equipmentModel}
              onChange={setEquipmentModel}
              load={listEquipmentModels}
            />
            <SuggestField label="Maker" placeholder="Aurelia" value={maker} onChange={setMaker} load={listMakers} />
            <label>
              Title
              <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="HX-200 brake service" />
            </label>
            <button type="submit">Upload manual</button>
          </form>
          {uploadError ? <p className="error">{uploadError}</p> : null}
          {job ? <JobStatus job={job} /> : null}
        </section>
        <section className="panel">
          <h2>Manuals</h2>
          <div className="library">
            {loadingLibrary ? <p className="muted">Loading manuals…</p> : null}
            {libraryError ? <p className="error">{libraryError}</p> : null}
            {!loadingLibrary && !libraryError && documents.length === 0 ? (
              <p className="muted">No manuals yet. Upload a PDF, Markdown, or text file.</p>
            ) : null}
            <ul>
              {documents.map((document) => (
                <ManualRow
                  key={document.documentId}
                  document={document}
                  open={openId === document.documentId}
                  onToggle={() =>
                    setOpenId((current) => (current === document.documentId ? null : document.documentId))
                  }
                />
              ))}
            </ul>
            <div className="pager">
              <button type="button" disabled={page <= 1 || loadingLibrary} onClick={() => setPage((current) => current - 1)}>
                Previous
              </button>
              <p className="muted">
                {count === 0 ? "0 manuals" : `${from}–${to} of ${count}`} · page {page} of {totalPages}
              </p>
              <button type="button" disabled={page >= totalPages || loadingLibrary} onClick={() => setPage((current) => current + 1)}>
                Next
              </button>
            </div>
          </div>
        </section>
      </div>
    </>
  );
}

function SuggestField({ label, placeholder, value, onChange, load }) {
  const [open, setOpen] = useState(false);
  const [options, setOptions] = useState([]);
  const [active, setActive] = useState(0);
  const requestId = useRef(0);

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    const current = requestId.current + 1;
    requestId.current = current;
    const timer = setTimeout(async () => {
      try {
        const { body } = await load(value);
        if (current !== requestId.current) {
          return;
        }
        const typed = value.trim().toLowerCase();
        setOptions((body.data?.objects || []).filter((name) => name.toLowerCase() !== typed));
        setActive(0);
      } catch {
        if (current === requestId.current) {
          setOptions([]);
        }
      }
    }, 200);
    return () => clearTimeout(timer);
  }, [load, open, value]);

  function choose(name) {
    onChange(name);
    setOpen(false);
    setOptions([]);
  }

  function onKeyDown(event) {
    if (!open || options.length === 0) {
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((index) => (index + 1) % options.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((index) => (index - 1 + options.length) % options.length);
    } else if (event.key === "Enter") {
      event.preventDefault();
      choose(options[active]);
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <label className="suggest">
      {label}
      <input
        value={value}
        placeholder={placeholder}
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={open && options.length > 0}
        onChange={(event) => {
          onChange(event.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={onKeyDown}
      />
      {open && options.length > 0 ? (
        <ul className="suggest-list" role="listbox">
          {options.map((name, index) => (
            <li key={name}>
              <button
                type="button"
                role="option"
                className={index === active ? "active" : ""}
                aria-selected={index === active}
                onMouseDown={(event) => {
                  event.preventDefault();
                  choose(name);
                }}
              >
                {name}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </label>
  );
}

function ManualRow({ document, open, onToggle }) {
  const indexed =
    document.chunkCount > 0
      ? `${document.pageCount} page${document.pageCount === 1 ? "" : "s"} · ${document.chunkCount} passage${document.chunkCount === 1 ? "" : "s"}`
      : null;
  return (
    <li>
      <button type="button" className="manual-row" aria-expanded={open} onClick={onToggle}>
        <strong>{document.title}</strong>
        <span>{document.maker ? `${document.maker} ${document.equipmentModel}` : document.equipmentModel}</span>
        <em className={document.status}>{document.status}</em>
        {document.failureReason ? <small>{document.failureReason}</small> : null}
      </button>
      {open ? (
        <dl className="manual-more">
          <dt>File</dt>
          <dd>
            <a
              href={`/api/v1/documents/${document.documentId}/file`}
              download={document.filename}
            >
              Download {document.filename}
            </a>
          </dd>
          <dt>Type</dt>
          <dd>{fileKind(document.mediaType)}</dd>
          {document.language ? (
            <>
              <dt>Language</dt>
              <dd>{document.language}</dd>
            </>
          ) : null}
          {indexed ? (
            <>
              <dt>Indexed</dt>
              <dd>{indexed}</dd>
            </>
          ) : null}
          <dt>Added</dt>
          <dd>{new Date(document.createdAt).toLocaleString()}</dd>
        </dl>
      ) : null}
    </li>
  );
}

function fileKind(mediaType) {
  if (mediaType === "application/pdf") {
    return "PDF";
  }
  if (mediaType === "text/markdown" || mediaType === "text/x-markdown") {
    return "Markdown";
  }
  if (mediaType === "text/plain") {
    return "Text";
  }
  return mediaType || "Unknown";
}

function JobStatus({ job }) {
  return (
    <p className={`job ${job.status}`}>
      {job.title}: {job.status}
      {job.failureReason ? ` — ${job.failureReason}` : ""}
    </p>
  );
}
