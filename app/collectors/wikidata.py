from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

from app.collectors.base import MalformedPayload
from app.collectors.http import SafeHttpClient


@dataclass(frozen=True)
class WikidataMatch:
    entity_id: str
    label: str
    aliases: tuple[str, ...]
    description: str | None
    instance_of: tuple[str, ...]


@dataclass(frozen=True)
class WikidataRawResponse:
    request_url: str
    raw_bytes: bytes
    collected_at: datetime
    parser_version: str = "wikidata-parser-v1"


@dataclass(frozen=True)
class WikidataLookup:
    matches: list[WikidataMatch]
    raw_responses: list[WikidataRawResponse]


class WikidataClient:
    collector_version = "wikidata-api-v1"

    def __init__(
        self,
        http: SafeHttpClient,
        endpoint: str,
        *,
        now: Callable[[], datetime] | None = None,
        limit: int = 5,
    ) -> None:
        self._http = http
        self._endpoint = endpoint
        self._now = now or (lambda: datetime.now(UTC))
        self._limit = limit

    async def lookup(self, query: str) -> WikidataLookup:
        search_url = self._url(
            action="wbsearchentities",
            search=query,
            language="ko",
            uselang="ko",
            type="item",
            limit=str(self._limit),
        )
        search_bytes = await self._http.get_bytes(search_url)
        responses = [self._response(search_url, search_bytes)]
        search = _json_object(search_bytes)
        results = search.get("search")
        if not isinstance(results, list):
            raise MalformedPayload("Wikidata search results are missing")
        ids = [item.get("id") for item in results if isinstance(item, dict)]
        entity_ids = [value for value in ids if isinstance(value, str) and value.startswith("Q")]
        if not entity_ids:
            return WikidataLookup(matches=[], raw_responses=responses)

        entities_url = self._url(
            action="wbgetentities",
            ids="|".join(entity_ids),
            props="labels|aliases|descriptions|claims",
            languages="ko|en",
        )
        entity_bytes = await self._http.get_bytes(entities_url)
        responses.append(self._response(entities_url, entity_bytes))
        payload = _json_object(entity_bytes)
        entities = payload.get("entities")
        if not isinstance(entities, dict):
            raise MalformedPayload("Wikidata entities are missing")
        matches = [
            _parse_entity(entity_id, entities.get(entity_id))
            for entity_id in entity_ids
            if entity_id in entities
        ]
        return WikidataLookup(matches=matches, raw_responses=responses)

    def _url(self, **params: str) -> str:
        return f"{self._endpoint}?{urlencode({'format': 'json', **params})}"

    def _response(self, url: str, raw_bytes: bytes) -> WikidataRawResponse:
        return WikidataRawResponse(url, raw_bytes, self._now().astimezone(UTC))


def _json_object(raw_bytes: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MalformedPayload("Wikidata returned malformed JSON") from exc
    if not isinstance(value, dict):
        raise MalformedPayload("Wikidata response must be an object")
    return value


def _parse_entity(entity_id: str, value: Any) -> WikidataMatch:
    if not isinstance(value, dict):
        raise MalformedPayload("Wikidata entity must be an object")
    labels = value.get("labels") if isinstance(value.get("labels"), dict) else {}
    descriptions = value.get("descriptions") if isinstance(value.get("descriptions"), dict) else {}
    aliases = value.get("aliases") if isinstance(value.get("aliases"), dict) else {}
    label = _language_value(labels, "ko") or _language_value(labels, "en")
    if label is None:
        raise MalformedPayload("Wikidata entity label is missing")
    alias_values: list[str] = []
    for language in ("ko", "en"):
        language_aliases = aliases.get(language)
        if isinstance(language_aliases, list):
            alias_values.extend(
                alias["value"]
                for alias in language_aliases
                if isinstance(alias, dict) and isinstance(alias.get("value"), str)
            )
        language_label = _language_value(labels, language)
        if language_label and language_label != label:
            alias_values.append(language_label)
    claims = value.get("claims") if isinstance(value.get("claims"), dict) else {}
    instance_of: list[str] = []
    for claim in claims.get("P31", []) if isinstance(claims.get("P31"), list) else []:
        try:
            claim_id = claim["mainsnak"]["datavalue"]["value"]["id"]
        except (KeyError, TypeError):
            continue
        if isinstance(claim_id, str):
            instance_of.append(claim_id)
    return WikidataMatch(
        entity_id=entity_id,
        label=label,
        aliases=tuple(dict.fromkeys(alias_values)),
        description=_language_value(descriptions, "ko") or _language_value(descriptions, "en"),
        instance_of=tuple(dict.fromkeys(instance_of)),
    )


def _language_value(values: dict[str, Any], language: str) -> str | None:
    value = values.get(language)
    if isinstance(value, dict) and isinstance(value.get("value"), str):
        return value["value"]
    return None
