"""Load the sample corpus when a tenant library is empty."""

import logging
from pathlib import Path

from sqlalchemy import func, select

from app.core.config import Settings
from app.db.models import DocumentRow
from app.db.session import session_scope
from app.schemas.documents import DocumentUploadRequest
from app.services.library import upload

logger = logging.getLogger(__name__)

_TITLES = {
    "hx-200-brakes.md": ("HX-200", "HX-200 brake service"),
    "hx-200-hydraulics.md": ("HX-200", "HX-200 hydraulic service"),
    "tu-9-antenna.md": ("TU-9", "TU-9 antenna installation"),
    "hx-200-columns.pdf": ("HX-200", "HX-200 two-column inspection note"),
}


def seed_corpus(settings: Settings) -> None:
    """Upload the sample manuals when this tenant has no documents. Existing uploads are left as they are."""
    directory = Path(settings.corpus_dir)
    if not directory.exists():
        logger.info("Corpus directory is missing: %s", directory)
        return
    with session_scope() as session:
        count = session.scalar(
            select(func.count()).select_from(DocumentRow).where(DocumentRow.tenant_id == settings.default_tenant)
        )
        if count:
            return
        for path in sorted(directory.iterdir()):
            if path.suffix.lower() not in {".md", ".txt", ".pdf"}:
                continue
            equipment, title = _TITLES.get(path.name, (path.stem, path.stem))
            upload(
                session,
                settings,
                tenant_id=settings.default_tenant,
                filename=path.name,
                media_type=None,
                raw=path.read_bytes(),
                metadata=DocumentUploadRequest(equipment_model=equipment, title=title),
            )
            logger.info("Seeded %s", path.name)
