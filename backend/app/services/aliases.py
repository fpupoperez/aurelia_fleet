"""Read and edit the feature spellings used by search."""

from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import AliasGroupRow, AliasTermRow
from app.domain.errors import DomainError

_TERM = re.compile(r"^[a-z0-9]{2,40}$")


def normalize_terms(terms: list[str]) -> list[str]:
    """Lowercase, trim, and deduplicate. A term must be one word, not a phrase."""
    cleaned: list[str] = []
    for raw in terms:
        term = raw.strip().lower()
        if not _TERM.fullmatch(term):
            raise DomainError("Each alias is 2 to 40 letters or digits, with no spaces.")
        if term not in cleaned:
            cleaned.append(term)
    if len(cleaned) < 2:
        raise DomainError("An alias group needs at least two different words.")
    return cleaned


def load_alias_groups(session: Session, tenant_id: str) -> tuple[frozenset[str], ...]:
    """The groups search uses to treat two spellings as one feature. One query."""
    rows = session.execute(
        select(AliasTermRow.group_id, AliasTermRow.term).where(AliasTermRow.tenant_id == tenant_id)
    ).all()
    grouped: dict[UUID, set[str]] = {}
    for group_id, term in rows:
        grouped.setdefault(group_id, set()).add(term)
    return tuple(frozenset(terms) for terms in grouped.values() if len(terms) >= 2)


def list_aliases(session: Session, tenant_id: str) -> list[tuple[AliasGroupRow, list[str]]]:
    """Every group and its terms for the alias screen."""
    groups = session.scalars(
        select(AliasGroupRow)
        .where(AliasGroupRow.tenant_id == tenant_id)
        .order_by(AliasGroupRow.created_at, AliasGroupRow.id)
    ).all()
    return [(group, _terms(session, group.id)) for group in groups]


def create_alias(session: Session, *, tenant_id: str, terms: list[str]) -> tuple[AliasGroupRow, list[str]]:
    """Store a new group. A term that already belongs to a group is rejected."""
    cleaned = normalize_terms(terms)
    _reject_taken(session, tenant_id, cleaned, None)
    group = AliasGroupRow(tenant_id=tenant_id)
    session.add(group)
    session.flush()
    _replace_terms(session, group, cleaned)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise DomainError("One of those words is already in another alias group.", status_code=409) from exc
    session.refresh(group)
    return group, cleaned


def update_alias(
    session: Session, *, tenant_id: str, alias_id: UUID, terms: list[str]
) -> tuple[AliasGroupRow, list[str]]:
    """Replace the terms of one group."""
    group = _group(session, tenant_id, alias_id)
    cleaned = normalize_terms(terms)
    _reject_taken(session, tenant_id, cleaned, group.id)
    _replace_terms(session, group, cleaned)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise DomainError("One of those words is already in another alias group.", status_code=409) from exc
    return group, cleaned


def delete_alias(session: Session, *, tenant_id: str, alias_id: UUID) -> tuple[AliasGroupRow, list[str]]:
    """Remove a group and its terms."""
    group = _group(session, tenant_id, alias_id)
    terms = _terms(session, group.id)
    session.delete(group)
    session.commit()
    return group, terms


def _group(session: Session, tenant_id: str, alias_id: UUID) -> AliasGroupRow:
    """One group in this tenant, or 404."""
    group = session.scalar(
        select(AliasGroupRow).where(AliasGroupRow.id == alias_id, AliasGroupRow.tenant_id == tenant_id)
    )
    if group is None:
        raise DomainError("Alias group not found.", status_code=404)
    return group


def _terms(session: Session, group_id: UUID) -> list[str]:
    """The spellings in one group, in stored order."""
    return list(
        session.scalars(select(AliasTermRow.term).where(AliasTermRow.group_id == group_id).order_by(AliasTermRow.term))
    )


def _reject_taken(session: Session, tenant_id: str, terms: list[str], group_id: UUID | None) -> None:
    """Refuse a term that another group in this tenant already uses."""
    query = select(AliasTermRow.term).where(AliasTermRow.tenant_id == tenant_id, AliasTermRow.term.in_(terms))
    if group_id is not None:
        query = query.where(AliasTermRow.group_id != group_id)
    taken = list(session.scalars(query))
    if taken:
        names = ", ".join(sorted(taken))
        raise DomainError(f"Already used in another group: {names}.", status_code=409)


def _replace_terms(session: Session, group: AliasGroupRow, terms: list[str]) -> None:
    """Delete the group's terms and insert the new list."""
    existing = session.scalars(select(AliasTermRow).where(AliasTermRow.group_id == group.id)).all()
    for row in existing:
        session.delete(row)
    session.flush()
    for term in terms:
        session.add(AliasTermRow(group_id=group.id, tenant_id=group.tenant_id, term=term))
