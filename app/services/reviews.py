from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import Category, ReviewAction, ReviewStatus
from app.models.tables import EntityAlias, EntityCandidate, Review, TrendEntity
from app.repositories.reviews import ReviewRepository


class ReviewError(ValueError):
    pass


class EntityNotFound(ReviewError):
    pass


class StaleReview(ReviewError):
    pass


@dataclass(frozen=True)
class ReviewCommand:
    entity_id: int
    action: ReviewAction
    expected_version: int
    actor: str
    reason: str | None = None
    category: Category | None = None
    target_entity_id: int | None = None
    candidate_ids: tuple[int, ...] = ()


class ReviewService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = ReviewRepository(session)

    def apply(self, command: ReviewCommand, now: datetime) -> Review:
        entity = self._repo.entity_for_update(command.entity_id)
        if entity is None:
            raise EntityNotFound(f"entity {command.entity_id} not found")
        if entity.version != command.expected_version:
            raise StaleReview(
                f"expected version {command.expected_version}, current version {entity.version}"
            )

        payload: dict[str, object] = {"previous_version": entity.version}
        if command.action is ReviewAction.APPROVE:
            entity.review_status = ReviewStatus.APPROVED
        elif command.action is ReviewAction.REJECT:
            entity.review_status = ReviewStatus.REJECTED
        elif command.action is ReviewAction.MARK_NOISE:
            entity.review_status = ReviewStatus.NOISE
        elif command.action is ReviewAction.CHANGE_CATEGORY:
            if command.category is None:
                raise ReviewError("CHANGE_CATEGORY requires category")
            payload["previous_category"] = entity.category.value if entity.category else None
            payload["category"] = command.category.value
            entity.category = command.category
        elif command.action is ReviewAction.MERGE:
            target = self._target(command, entity)
            self._merge(entity, target)
            payload["target_entity_id"] = target.id
            entity.review_status = ReviewStatus.REJECTED
            target.version += 1
            target.updated_at = now
        elif command.action is ReviewAction.SPLIT:
            target = self._target(command, entity)
            if not command.candidate_ids:
                raise ReviewError("SPLIT requires candidate_ids")
            links = list(
                self._session.scalars(
                    select(EntityCandidate).where(
                        EntityCandidate.entity_id == entity.id,
                        EntityCandidate.candidate_id.in_(command.candidate_ids),
                    )
                )
            )
            if len(links) != len(set(command.candidate_ids)):
                raise ReviewError("SPLIT candidate_ids must all belong to the source entity")
            for link in links:
                link.entity_id = target.id
            payload["target_entity_id"] = target.id
            payload["candidate_ids"] = list(command.candidate_ids)
            target.version += 1
            target.updated_at = now
        else:  # pragma: no cover - exhaustive enum guard
            raise ReviewError(f"unsupported review action: {command.action.value}")

        entity.version += 1
        entity.updated_at = now
        payload["new_version"] = entity.version
        return self._repo.add(
            Review(
                entity_id=entity.id,
                action=command.action,
                actor=command.actor,
                reason=command.reason,
                payload=payload,
                created_at=now,
            )
        )

    def _target(self, command: ReviewCommand, source: TrendEntity) -> TrendEntity:
        if command.target_entity_id is None or command.target_entity_id == source.id:
            raise ReviewError(f"{command.action.value} requires a different target_entity_id")
        target = self._repo.entity_for_update(command.target_entity_id)
        if target is None:
            raise EntityNotFound(f"entity {command.target_entity_id} not found")
        return target

    def _merge(self, source: TrendEntity, target: TrendEntity) -> None:
        links = self._session.scalars(
            select(EntityCandidate).where(EntityCandidate.entity_id == source.id)
        )
        for link in links:
            link.entity_id = target.id
        target_aliases = {
            (alias.normalized_alias, alias.language)
            for alias in self._session.scalars(
                select(EntityAlias).where(EntityAlias.entity_id == target.id)
            )
        }
        source_aliases = list(
            self._session.scalars(
                select(EntityAlias).where(EntityAlias.entity_id == source.id)
            )
        )
        for alias in source_aliases:
            key = (alias.normalized_alias, alias.language)
            if key in target_aliases:
                self._session.delete(alias)
            else:
                alias.entity_id = target.id
                target_aliases.add(key)
