"""Download the original uploaded bytes without loading them as one string."""

import json
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import DocumentRow
from app.db.session import session_scope


def test_download_streams_the_original_file(client: TestClient) -> None:
    payload = b"brake pad " * 9000
    assert len(payload) > 64 * 1024
    prefix = client.app.state.settings.api_prefix
    created = client.post(
        f"{prefix}/documents",
        files={"file": ("brakes.txt", payload, "text/plain")},
        data={"metadata": json.dumps({"equipmentModel": "HX-200", "title": "HX-200 brakes"})},
    )
    assert created.status_code == 201, created.text
    document_id = created.json()["data"]["documentId"]

    with client.stream("GET", f"{prefix}/documents/{document_id}/file") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")
        assert 'filename="brakes.txt"' in response.headers["content-disposition"]
        received = bytearray()
        for chunk in response.iter_bytes():
            received.extend(chunk)
    assert bytes(received) == payload

    missing = client.get(f"{prefix}/documents/00000000-0000-0000-0000-000000000099/file")
    assert missing.status_code == 404
    assert missing.json()["success"] is False


def test_download_refuses_a_path_outside_the_upload_directory(client: TestClient) -> None:
    prefix = client.app.state.settings.api_prefix
    created = client.post(
        f"{prefix}/documents",
        files={"file": ("note.txt", b"keep this local", "text/plain")},
        data={"metadata": json.dumps({"equipmentModel": "HX-200", "title": "Local note"})},
    )
    document_id = created.json()["data"]["documentId"]
    with session_scope() as session:
        document = session.scalar(select(DocumentRow).where(DocumentRow.id == UUID(document_id)))
        document.storage_path = "/etc/passwd"
    response = client.get(f"{prefix}/documents/{document_id}/file")
    assert response.status_code == 404
    assert "passwd" not in response.text
