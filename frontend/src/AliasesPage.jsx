/** Alias page. Each row is a group of spellings search treats as one feature. */
import { useEffect, useState } from "react";
import { createAlias, deleteAlias, listAliases, updateAlias } from "./api";

/** Split the comma-separated field into the terms the API stores. */
function splitTerms(value) {
  return value
    .split(",")
    .map((term) => term.trim())
    .filter(Boolean);
}

export function AliasesPage() {
  const [groups, setGroups] = useState([]);
  const [drafts, setDrafts] = useState({});
  const [fresh, setFresh] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function refresh() {
    setLoading(true);
    try {
      const { body } = await listAliases();
      const objects = body.data?.objects || [];
      setGroups(objects);
      setDrafts(Object.fromEntries(objects.map((group) => [group.aliasId, group.terms.join(", ")])));
      setError("");
    } catch (caught) {
      setError(caught.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function onAdd(event) {
    event.preventDefault();
    setError("");
    try {
      await createAlias(splitTerms(fresh));
      setFresh("");
      await refresh();
    } catch (caught) {
      setError(caught.message);
    }
  }

  async function onSave(aliasId) {
    setError("");
    try {
      await updateAlias(aliasId, splitTerms(drafts[aliasId] || ""));
      await refresh();
    } catch (caught) {
      setError(caught.message);
    }
  }

  async function onDelete(aliasId) {
    setError("");
    try {
      await deleteAlias(aliasId);
      await refresh();
    } catch (caught) {
      setError(caught.message);
    }
  }

  return (
    <>
      <header className="mast">
        <p className="eyebrow">Aurelia Fleet Services</p>
        <h1>Aliases</h1>
        <p className="lede">
          Words in one group are the same feature. A question that says bluetooth also finds manuals that only say ble.
        </p>
      </header>
      <section className="panel">
        <h2>Add a group</h2>
        <form className="alias-add" onSubmit={onAdd}>
          <label>
            Words, separated by commas
            <input
              value={fresh}
              onChange={(event) => setFresh(event.target.value)}
              placeholder="gnss, gps"
            />
          </label>
          <button type="submit">Add alias</button>
        </form>
        {error ? <p className="error">{error}</p> : null}
        <h2>Groups</h2>
        {loading ? <p className="muted">Loading aliases…</p> : null}
        {!loading && groups.length === 0 ? <p className="muted">No alias groups yet.</p> : null}
        <ul className="alias-list">
          {groups.map((group) => (
            <li key={group.aliasId}>
              <input
                aria-label="Alias words"
                value={drafts[group.aliasId] || ""}
                onChange={(event) =>
                  setDrafts((current) => ({ ...current, [group.aliasId]: event.target.value }))
                }
              />
              <div className="alias-actions">
                <button type="button" onClick={() => onSave(group.aliasId)}>
                  Save
                </button>
                <button type="button" className="quiet" onClick={() => onDelete(group.aliasId)}>
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}
