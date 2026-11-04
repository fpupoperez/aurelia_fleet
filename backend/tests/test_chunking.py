"""Chunk windows stay inside a page and overlap."""

from app.ingest.chunking import chunk_pages, markdown_sections


def test_chunks_do_not_cross_pages() -> None:
    pages = [(1, "alpha " * 30), (2, "beta " * 30)]
    drafts = chunk_pages(pages, size=40, overlap=10)
    assert drafts
    assert all(draft.page == 1 or "beta" in draft.content for draft in drafts)
    assert all("alpha" not in draft.content or draft.page == 1 for draft in drafts)
    assert all("beta" not in draft.content or draft.page == 2 for draft in drafts)


def test_overlap_is_shared() -> None:
    text = " ".join(f"word{index}" for index in range(80))
    drafts = chunk_pages([(1, text)], size=100, overlap=20)
    assert len(drafts) >= 2
    assert drafts[0].content[-15:] in text
    assert drafts[1].content[:10] in text


def test_empty_input() -> None:
    assert chunk_pages([(1, "   ")], size=100, overlap=10) == []


def test_markdown_sections_are_numbered() -> None:
    pages = markdown_sections("# Brakes\nPad thickness.\n# Torque\n210 Nm.")
    assert [page for page, _ in pages] == [1, 2]
    assert "Pad thickness" in pages[0][1]
    assert "210 Nm" in pages[1][1]
