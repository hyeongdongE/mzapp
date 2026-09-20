from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import ResolutionStatus, ReviewStatus
from app.models.tables import EntityAlias, EntityCandidate, TrendEntity
from app.pipeline.normalization import normalize_text


class EntityRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def entities_by_alias(self, normalized_alias: str) -> list[TrendEntity]:
        alias_entities = list(
            self._session.scalars(
                select(TrendEntity)
                .join(EntityAlias, EntityAlias.entity_id == TrendEntity.id)
                .where(EntityAlias.normalized_alias == normalized_alias)
                .distinct()
            )
        )
        named_entities = list(
            self._session.scalars(
                select(TrendEntity).where(TrendEntity.normalized_name == normalized_alias)
            )
        )
        return list({entity.id: entity for entity in [*alias_entities, *named_entities]}.values())

    def by_wikidata_id(self, wikidata_id: str) -> TrendEntity | None:
        return self._session.scalar(
            select(TrendEntity).where(TrendEntity.wikidata_id == wikidata_id)
        )

    def create_entity(
        self,
        *,
        canonical_name: str,
        normalized_name: str,
        wikidata_id: str | None,
        entity_type: str | None,
    ) -> TrendEntity:
        entity = TrendEntity(
            canonical_name=canonical_name,
            normalized_name=normalized_name,
            wikidata_id=wikidata_id,
            entity_type=entity_type,
            resolution_status=ResolutionStatus.RESOLVED,
            review_status=ReviewStatus.PENDING,
            version=1,
        )
        self._session.add(entity)
        self._session.flush()
        return entity

    def add_alias(self, entity_id: int, alias: str, language: str = "und") -> None:
        normalized = normalize_text(alias)
        existing = self._session.scalar(
            select(EntityAlias).where(
                EntityAlias.entity_id == entity_id,
                EntityAlias.normalized_alias == normalized,
                EntityAlias.language == language,
            )
        )
        if existing is None:
            self._session.add(
                EntityAlias(
                    entity_id=entity_id,
                    alias=alias,
                    normalized_alias=normalized,
                    language=language,
                )
            )

    def link_candidate(self, entity_id: int, candidate_id: int, reason: str) -> None:
        existing = self._session.scalar(
            select(EntityCandidate).where(
                EntityCandidate.entity_id == entity_id,
                EntityCandidate.candidate_id == candidate_id,
            )
        )
        if existing is None:
            self._session.add(
                EntityCandidate(
                    entity_id=entity_id,
                    candidate_id=candidate_id,
                    entity_version="entity-v1",
                    match_reason=reason,
                )
            )
        self._session.flush()
