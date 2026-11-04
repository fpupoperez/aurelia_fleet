/** Ask on `/`, the library on `/library`, and feature spellings on `/aliases`. */
import { useEffect, useState } from "react";
import { AliasesPage } from "./AliasesPage";
import { AskPage } from "./AskPage";
import { LibraryPage } from "./LibraryPage";

export function App() {
  const [path, setPath] = useState(window.location.pathname);

  useEffect(() => {
    const onPop = () => setPath(window.location.pathname);
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  function navigate(event, href) {
    event.preventDefault();
    if (window.location.pathname !== href) {
      window.history.pushState({}, "", href);
      setPath(href);
    }
  }

  const page = path === "/library" ? "library" : path === "/aliases" ? "aliases" : "ask";

  return (
    <div className="shell">
      <header className="topbar">
        <a className="brand" href="/" onClick={(event) => navigate(event, "/")}>
          Aurelia
        </a>
        <nav className="nav">
          <a className={page === "ask" ? "active" : ""} href="/" onClick={(event) => navigate(event, "/")}>
            Questions
          </a>
          <a className={page === "library" ? "active" : ""} href="/library" onClick={(event) => navigate(event, "/library")}>
            Library
          </a>
          <a className={page === "aliases" ? "active" : ""} href="/aliases" onClick={(event) => navigate(event, "/aliases")}>
            Aliases
          </a>
        </nav>
      </header>
      <main className="page">
        {page === "library" ? <LibraryPage /> : page === "aliases" ? <AliasesPage /> : <AskPage />}
      </main>
    </div>
  );
}
