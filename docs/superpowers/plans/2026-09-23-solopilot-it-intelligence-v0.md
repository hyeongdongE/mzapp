# SoloPilot IT Intelligence V0 First Vertical Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a real-data SoloPilot pipeline that conservatively turns GeekNews, Hacker News, GitHub Releases, Cloudflare, and AWS records into an evidence-grounded, five-minute Daily Brief rendered by the Today UI.

**Architecture:** Extend the existing FastAPI/PostgreSQL modular monolith with an isolated `app.intelligence` package while retaining existing collection provenance and replay. Additive tables hold normalized items, conservative clusters, evidence/fact provenance, assessments, and versioned briefs; deterministic rules own factual gates and ambiguous merges, while synthesis remains evidence-constrained with a deterministic fallback. The existing React PWA gains `/today` without removing `/saved`, and existing Trend Radar code remains available but disabled from the new default source registry where specified.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16, httpx, APScheduler, pytest, React 19, TypeScript, Vite, Vitest.

**Spec:** `docs/superpowers/specs/2026-09-23-solopilot-it-intelligence-v0-design.md`

## Global Constraints

- Canonical base is commit `a229c14`; implementation branch is `codex/solopilot-it-intelligence-v0`.
- All schema changes are additive; existing migrations, Google Trends/Wikimedia data, Personal Automation files, and Trend Radar routes must not be deleted.
- `SourceDefinition`/`SourcePolicy` are static configuration; `SourceHealth` is separate mutable runtime state.
- `RawItem` references immutable `RawFetch` provenance and never embeds or replaces the raw payload.
- Incorrect Merge is more severe than Duplicate Escape; ambiguous candidates remain unmerged and reviewable.
- Source count is never a merge condition; the four-source case is a Golden Fixture only.
- Evidence confidence and importance are stored and evaluated independently.
- Every published FACT must be traceable through `BriefItemFact → EventFact → EventFactEvidence → EventEvidence`.
- Normal briefs contain three to seven items; healthy `LOW_SIGNAL_DAY` briefs may contain one or two; `DEGRADED_SOURCE_COVERAGE` blocks publication.
- Reading time is a hard publication gate at 300 seconds.
- GeekNews public output defaults to title, attribution, and links; source summary/snippet redistribution is disabled.
- `/saved` remains for existing Trend cards; saving new BriefItems is Slice 2 and must not be implemented here.
- Long-horizon Trend inference, Radar expansion, personalization, X, arXiv, Hugging Face, Ask SoloPilot, RAG, and internal package/repository renames are out of scope.

## Review Focus

- Same entity, same day, different action or release must remain separate; pinned by Golden Hard Negative clustering tests in Task 4.
- A source that last succeeded before the brief window must cause `DEGRADED_SOURCE_COVERAGE`, not `LOW_SIGNAL_DAY`; pinned by publication tests in Task 6.
- A late item for an already briefed event must enrich provenance without ranking as a new event; pinned by window tests in Task 6.
- A FACT whose evidence becomes missing or non-publishable must fail the gate even when its event confidence is high; pinned by provenance tests in Task 5 and gate tests in Task 6.
- Mixed Korean/Latin content near 300 seconds must be shortened or rejected deterministically; pinned by reading-time tests in Task 6.

---

### Task 1: Add Source Registry, Runtime Health, and Intelligence Persistence

**Files:**
- Create: `app/intelligence/__init__.py`
- Create: `app/intelligence/sources.py`
- Create: `alembic/versions/0011_it_intelligence_slice.py`
- Modify: `app/models/enums.py`
- Modify: `app/models/tables.py`
- Test: `tests/intelligence/test_source_registry.py`
- Test support: `tests/intelligence/conftest.py`
- Test: `tests/models/test_intelligence_schema.py`
- Test: `tests/integration/test_migration_0011.py`

**Interfaces:**
- Produces: `SourceDefinition`, `SourcePolicy`, `SOURCE_REGISTRY`, and `required_source_keys()`.
- Produces: SQLAlchemy models `SourceHealth`, `RawItem`, `EventCluster`, `EventClusterItem`, `IntelligenceEntity`, `EventEntityLink`, `EventEvidence`, `EventFact`, `EventFactEvidence`, `EventAssessment`, `DailyBrief`, `BriefItem`, and `BriefItemFact`.
- Produces enums `SourceType`, `EvidenceKind`, `ClusterStatus`, `EvidenceConfidence`, `BriefStatus`, and the new `Source` values consumed by every later task.

- [ ] **Step 1: Write failing registry and schema tests**

```python
def test_registry_keeps_policy_separate_from_runtime_health() -> None:
    geeknews = SOURCE_REGISTRY[Source.GEEKNEWS]
    assert geeknews.policy.public_summary is False
    assert not hasattr(geeknews, "last_success_at")


def test_google_and_wikimedia_are_disabled_for_intelligence_by_default() -> None:
    assert SOURCE_REGISTRY[Source.GOOGLE_TRENDS].enabled is False
    assert SOURCE_REGISTRY[Source.WIKIMEDIA].enabled is False
    assert set(required_source_keys()) == {
        Source.GEEKNEWS,
        Source.HACKER_NEWS,
        Source.GITHUB_RELEASES,
        Source.OFFICIAL_CLOUDFLARE,
        Source.OFFICIAL_AWS,
    }


def test_fact_level_provenance_foreign_keys_are_present() -> None:
    fact_evidence = Base.metadata.tables["event_fact_evidence"]
    brief_fact = Base.metadata.tables["brief_item_facts"]
    assert {fk.target_fullname for fk in fact_evidence.foreign_keys} == {
        "event_facts.id", "event_evidence.id"
    }
    assert {fk.target_fullname for fk in brief_fact.foreign_keys} == {
        "brief_items.id", "event_facts.id", "event_evidence.id"
    }
```

- [ ] **Step 2: Run the focused tests and verify the missing imports/tables fail**

Run: `.venv/Scripts/python -m pytest tests/intelligence/test_source_registry.py tests/models/test_intelligence_schema.py tests/integration/test_migration_0011.py -q`

Expected: FAIL because `app.intelligence.sources`, new enums, and migration `0011` do not exist.

- [ ] **Step 3: Implement the source definitions and policy registry**

```python
@dataclass(frozen=True)
class SourcePolicy:
    store_full_content: bool
    public_title: bool = True
    public_link: bool = True
    public_attribution: bool = True
    public_summary: bool = False


@dataclass(frozen=True)
class SourceDefinition:
    source: Source
    display_name: str
    source_type: SourceType
    collection_method: str
    authority_level: int
    enabled: bool
    policy: SourcePolicy
    expected_freshness: timedelta
```

Seed exactly five enabled definitions and two disabled legacy definitions. Keep endpoint URLs in `Settings`; do not put mutable health fields in these dataclasses.

- [ ] **Step 4: Add enums, SQLAlchemy models, and additive migration**

Implement the exact tables named in Interfaces. Required uniqueness includes `(source, external_id, normalizer_version)` for `raw_items`, one active membership per raw item, `(brief_date, version)` for `daily_briefs`, and `(brief_id, position)` for `brief_items`. Add indexes for source/published time, cluster status/last seen, evidence event/kind, and brief date/status.

- [ ] **Step 5: Run focused tests and migration upgrade/downgrade/upgrade verification**

Run: `.venv/Scripts/python -m pytest tests/intelligence/test_source_registry.py tests/models/test_intelligence_schema.py tests/integration/test_migration_0011.py -q`

Expected: PASS, including migration from `0010 → 0011`, downgrade to `0010`, and re-upgrade to `0011` in the isolated migration fixture.

- [ ] **Step 6: Commit Task 1**

```powershell
git add app/intelligence app/models/enums.py app/models/tables.py alembic/versions/0011_it_intelligence_slice.py tests/intelligence tests/models/test_intelligence_schema.py tests/integration/test_migration_0011.py
git commit -m "feat: add intelligence source and persistence model"
```

### Task 2: Collect Five Enabled Sources into Provenance-Linked RawItems

**Files:**
- Create: `app/collectors/hacker_news.py`
- Create: `app/collectors/github_releases.py`
- Create: `app/collectors/official_feed.py`
- Create: `app/intelligence/normalization.py`
- Create: `app/services/intelligence_collection.py`
- Modify: `app/collectors/base.py`
- Modify: `app/services/collection.py`
- Modify: `app/repositories/collection.py`
- Modify: `app/config/settings.py`
- Modify: `scripts/collect.py`
- Test: `tests/collectors/test_hacker_news.py`
- Test: `tests/collectors/test_github_releases.py`
- Test: `tests/collectors/test_official_feed.py`
- Test support: `tests/collectors/conftest.py`
- Test: `tests/services/test_intelligence_collection.py`
- Fixtures: `tests/fixtures/hacker_news_topstories.json`
- Fixtures: `tests/fixtures/hacker_news_items.json`
- Fixtures: `tests/fixtures/github_releases.json`
- Fixtures: `tests/fixtures/cloudflare_feed.xml`
- Fixtures: `tests/fixtures/aws_feed.xml`

**Interfaces:**
- Consumes: `SOURCE_REGISTRY`, `SourceHealth`, `RawItem`, and existing `CollectionService` provenance tables.
- Produces: collectors returning `CollectionBatch` whose `SourceItem.metadata` contains normalized source fields.
- Produces: `IntelligenceCollectionService.run(collector, *, as_of, run_key) -> IntelligencePersistResult`.

- [ ] **Step 1: Write failing adapter contract tests**

```python
@pytest.mark.asyncio
async def test_hn_collector_preserves_topstory_and_item_payloads(fake_http) -> None:
    batch = await HackerNewsCollector(fake_http, max_items=30).collect(AS_OF)
    assert batch.source is Source.HACKER_NEWS
    assert batch.items[0].metadata["hn_score"] == 412
    assert batch.items[0].metadata["original_url"].startswith("https://")
    envelope = json.loads(batch.raw_bytes)
    assert envelope["top_story_ids"]
    assert envelope["items"]


def test_geeknews_normalization_does_not_publish_source_summary() -> None:
    source_item = SourceItem(
        source_item_id="geeknews:42",
        source_timestamp=AS_OF,
        observed_at=AS_OF,
        canonical_text="SoloPilot release",
        source_url="https://news.hada.io/topic?id=42",
        metrics={},
        title="SoloPilot release",
        snippet="GeekNews-authored summary that must remain private",
        metadata={"attribution": "GeekNews"},
    )
    item = normalize_source_item(Source.GEEKNEWS, source_item, raw_fetch_id=7)
    assert item.snippet is None
    assert item.metadata["attribution"] == "GeekNews"
```

- [ ] **Step 2: Run adapter tests and verify they fail**

Run: `.venv/Scripts/python -m pytest tests/collectors/test_hacker_news.py tests/collectors/test_github_releases.py tests/collectors/test_official_feed.py tests/services/test_intelligence_collection.py -q`

Expected: FAIL because the adapters and intelligence collection service do not exist.

- [ ] **Step 3: Extend SourceItem without breaking existing collectors**

Add optional fields with defaults after existing required fields:

```python
title: str | None = None
original_url: str | None = None
author: str | None = None
snippet: str | None = None
metadata: dict[str, JsonValue] = field(default_factory=dict)
```

Add `fetch_id` to `PersistResult` and expose the existing failure writer as `CollectionService.record_failure(...)`; keep every existing call site valid and retain `CollectionService.run(...)` behavior for legacy collectors.

- [ ] **Step 4: Implement adapters and safe endpoint settings**

Use the official HN Firebase endpoints, GitHub REST Releases endpoints for a fixed configured watchlist, `https://blog.cloudflare.com/rss/`, and `https://aws.amazon.com/blogs/aws/feed/`. Validate HTTPS hosts in `Settings`. HN stores one deterministic JSON envelope containing topstory IDs, each requested item response, and request URLs so replay has the exact acquisition input. GitHub creates one collector instance per configured repository.

- [ ] **Step 5: Implement RawItem normalization and runtime health updates**

```python
class IntelligenceCollectionService:
    async def run(self, collector: Collector, *, as_of: datetime, run_key: str) -> IntelligencePersistResult:
        try:
            batch = await collector.collect(as_of)
        except CollectorError as exc:
            self._provenance.record_failure(
                collector.source,
                run_key,
                started_at=self._now(),
                completed_at=self._now(),
                error_code=exc.code,
            )
            self._health.record_failure(collector.source, at=self._now(), code=exc.code)
            self._session.flush()
            raise
        persisted = self._provenance.persist(batch, run_key=run_key)
        inserted = self._raw_items.persist_batch(
            source=batch.source,
            items=batch.items,
            raw_fetch_id=persisted.fetch_id,
            normalizer_version="it-normalizer-v1",
        )
        self._health.record_success(
            collector.source,
            at=self._now(),
            covered_through=as_of,
        )
        self._session.flush()
        return IntelligencePersistResult(
            run_id=persisted.run_id,
            fetch_id=persisted.fetch_id,
            inserted_raw_items=inserted,
        )
```

Canonicalize URLs by lowercasing hosts, removing fragments and known tracking parameters, normalizing default ports, and preserving path/query parameters that identify releases or stories. Hash only policy-allowed normalized content.

- [ ] **Step 6: Run adapter, collection, and existing provenance/replay tests**

Run: `.venv/Scripts/python -m pytest tests/collectors tests/services/test_collection.py tests/services/test_replay.py tests/services/test_intelligence_collection.py -q`

Expected: PASS; existing GeekNews parser-version replay semantics remain unchanged.

- [ ] **Step 7: Commit Task 2**

```powershell
git add app/collectors app/intelligence/normalization.py app/services/collection.py app/services/intelligence_collection.py app/repositories/collection.py app/config/settings.py scripts/collect.py tests/collectors tests/services tests/fixtures
git commit -m "feat: collect intelligence sources into raw items"
```

### Task 3: Implement Deterministic Deduplication and the 50-Item Golden Dataset

**Files:**
- Create: `app/intelligence/deduplication.py`
- Create: `tests/intelligence/golden/raw_items.json`
- Create: `tests/intelligence/golden/expected.json`
- Create: `tests/intelligence/golden/loader.py`
- Test: `tests/intelligence/test_deduplication.py`
- Test: `tests/intelligence/test_golden_dataset.py`

**Interfaces:**
- Consumes: persisted `RawItem` fields from Task 2.
- Produces: `DuplicateDecision(kind, matched_item_id, reason_codes)` and `Deduplicator.decide(candidate, existing) -> DuplicateDecision`.
- Produces: at least 50 stable Golden RawItems used by Tasks 4–6.

- [ ] **Step 1: Create the Golden Dataset and assert its composition**

```python
def test_golden_dataset_has_required_positive_and_hard_negative_groups() -> None:
    dataset = load_golden_dataset()
    assert len(dataset.items) >= 50
    assert dataset.group("four-source-same-event").expected_cluster_count == 1
    assert dataset.group("same-entity-different-event").expected_cluster_count >= 2
    assert dataset.group("same-day-different-release").expected_cluster_count >= 2
    assert dataset.group("follow-up-vs-new-event").expected_cluster_count >= 2
```

The fixture must contain deterministic timestamps, URLs, external IDs, entities, expected duplicate groups, expected event groups, confidence expectations, importance ordering, and brief inclusion labels.

- [ ] **Step 2: Write failing deduplication tests**

Cover same external ID, canonical URL, tracking-only URL differences, content hash, GitHub repository/release ID, title-only non-duplicate, and two different releases with similar titles.

- [ ] **Step 3: Run the focused tests and verify failure**

Run: `.venv/Scripts/python -m pytest tests/intelligence/test_deduplication.py tests/intelligence/test_golden_dataset.py -q`

Expected: FAIL because `Deduplicator` is missing.

- [ ] **Step 4: Implement deterministic deduplication**

```python
class DuplicateKind(StrEnum):
    EXACT = "EXACT"
    DISTINCT = "DISTINCT"


@dataclass(frozen=True)
class DuplicateDecision:
    kind: DuplicateKind
    matched_item_id: int | None
    reason_codes: tuple[str, ...]
```

Return `EXACT` only for the spec's deterministic identities. Never use source count or title similarity alone.

- [ ] **Step 5: Run Golden deduplication tests**

Run: `.venv/Scripts/python -m pytest tests/intelligence/test_deduplication.py tests/intelligence/test_golden_dataset.py -q`

Expected: PASS with zero false duplicate matches in Hard Negative groups.

- [ ] **Step 6: Commit Task 3**

```powershell
git add app/intelligence/deduplication.py tests/intelligence
git commit -m "feat: add conservative raw item deduplication"
```

### Task 4: Build Conservative Event Clusters, Entities, and Evidence

**Files:**
- Create: `app/intelligence/clustering.py`
- Create: `app/intelligence/entities.py`
- Create: `app/intelligence/evidence.py`
- Create: `app/services/event_processing.py`
- Test: `tests/intelligence/test_clustering.py`
- Test: `tests/intelligence/test_entities.py`
- Test: `tests/intelligence/test_evidence.py`
- Test: `tests/services/test_event_processing.py`

**Interfaces:**
- Consumes: `RawItem`, `Deduplicator`, Golden Dataset.
- Produces: `ClusterAction` and `ClusterDecision(action, cluster_id, score, reason_codes)` where action is `MERGE`, `NEW`, or `REVIEW`.
- Produces: `EventProcessingService.process_window(window_start, window_end, *, version) -> EventProcessingResult`.
- Produces persisted `EventCluster`, `EventClusterItem`, `IntelligenceEntity`, `EventEntityLink`, and `EventEvidence` rows.

- [ ] **Step 1: Write failing positive and Hard Negative cluster tests**

```python
def test_four_sources_for_one_known_event_form_one_cluster(golden_items) -> None:
    result = ConservativeClusterer().process(
        golden_items.group("four-source-same-event")
    )
    assert len(result.clusters) == 1
    assert result.clusters[0].source_count == 4


@pytest.mark.parametrize("group", [
    "same-entity-different-event",
    "same-day-different-release",
    "follow-up-vs-new-event",
])
def test_hard_negatives_do_not_auto_merge(group, golden_items) -> None:
    result = ConservativeClusterer().process(golden_items.group(group))
    assert result.incorrect_merge_count == 0
    assert all(decision.action in {ClusterAction.NEW, ClusterAction.REVIEW} for decision in result.decisions)
```

- [ ] **Step 2: Run cluster tests and verify failure**

Run: `.venv/Scripts/python -m pytest tests/intelligence/test_clustering.py tests/intelligence/test_entities.py tests/intelligence/test_evidence.py tests/services/test_event_processing.py -q`

Expected: FAIL because the event-processing package is absent.

- [ ] **Step 3: Implement conservative feature extraction and decisions**

Automatic merge requires a deterministic shared target or a high-precision tuple of compatible entities, action/release identifier, title similarity, and publication window. Borderline scores return `REVIEW`; they never mutate membership. Persist reason codes and the clustering version for replay.

- [ ] **Step 4: Implement deterministic entity and evidence extraction**

Extract curated entity aliases and GitHub owner/repository/product tokens without requiring Wikidata. Classify evidence from `SourceDefinition.source_type`; preserve `RawItem` and source URL links. Treat official feeds and maintainer releases as stronger evidence classes without changing importance.

- [ ] **Step 5: Run focused and Golden clustering tests**

Run: `.venv/Scripts/python -m pytest tests/intelligence/test_clustering.py tests/intelligence/test_entities.py tests/intelligence/test_evidence.py tests/services/test_event_processing.py tests/intelligence/test_golden_dataset.py -q`

Expected: PASS, with Golden `incorrect_merge_count == 0` and the four-source fixture producing one cluster for event-identity reasons rather than source count.

- [ ] **Step 6: Commit Task 4**

```powershell
git add app/intelligence/clustering.py app/intelligence/entities.py app/intelligence/evidence.py app/services/event_processing.py tests/intelligence tests/services/test_event_processing.py
git commit -m "feat: cluster intelligence events conservatively"
```

### Task 5: Add Fact Provenance, Evidence Confidence, and Importance

**Files:**
- Create: `app/intelligence/facts.py`
- Create: `app/intelligence/assessment.py`
- Create: `app/intelligence/synthesis.py`
- Test: `tests/intelligence/test_facts.py`
- Test: `tests/intelligence/test_assessment.py`
- Test: `tests/intelligence/test_synthesis.py`

**Interfaces:**
- Consumes: clusters, entities, and evidence from Task 4.
- Produces: `FactBuilder.build(event_id) -> list[ValidatedFact]` and persisted fact/evidence links.
- Produces: `AssessmentService.assess(event_id, *, version) -> EventAssessmentResult` with separate `confidence` and `importance`.
- Produces: `EvidenceOnlySynthesizer.synthesize(event_id) -> BriefDraftContent` containing headline, what happened, why it matters, FACT, INTERPRETATION, WATCH, and fact IDs.

- [ ] **Step 1: Write failing fact-provenance tests**

```python
def test_every_publishable_fact_has_exact_supporting_evidence(session, event) -> None:
    facts = FactBuilder(session).build(event.id)
    assert facts
    assert all(fact.publishable and fact.evidence_ids for fact in facts)


def test_fact_with_missing_evidence_is_not_publishable(session, event) -> None:
    fact = FactBuilder(session).build(event.id)[0]
    session.query(EventFactEvidence).filter_by(fact_id=fact.id).delete()
    assert FactValidator(session).validate(fact.id).publishable is False
```

- [ ] **Step 2: Write failing independent assessment tests**

Pin high-confidence/low-importance official maintenance, low-confidence/high-interest rumor, strong diverse evidence, duplicated syndication, and ambiguity penalties. Assert changing confidence inputs never changes the stored importance component values and vice versa.

- [ ] **Step 3: Run focused tests and verify failure**

Run: `.venv/Scripts/python -m pytest tests/intelligence/test_facts.py tests/intelligence/test_assessment.py tests/intelligence/test_synthesis.py -q`

Expected: FAIL because fact and assessment services are missing.

- [ ] **Step 4: Implement fact building and claim-level provenance**

Build structured facts only from allowed source fields: title/action, publisher, publication date, release tag, repository, and deterministic metrics. Persist `EventFactEvidence` for each support. Do not copy GeekNews summary/snippet into facts or public synthesis.

- [ ] **Step 5: Implement independent confidence and importance rules**

```python
@dataclass(frozen=True)
class EventAssessmentResult:
    confidence: EvidenceConfidence
    confidence_breakdown: dict[str, float | str | bool]
    importance: float
    importance_breakdown: dict[str, float | str | bool]
```

Confidence must gate publication before importance ranking. Source diversity counts independent source types only after duplicate/syndication collapse.

- [ ] **Step 6: Implement evidence-only synthesis and unsupported-claim validation**

The fallback synthesizer composes Korean copy from validated facts and labeled interpretation/watch templates. Validate all names, versions, dates, and numbers against the fact set. Return fact IDs with the draft so Task 6 can snapshot provenance.

- [ ] **Step 7: Run focused and Golden assessment tests**

Run: `.venv/Scripts/python -m pytest tests/intelligence/test_facts.py tests/intelligence/test_assessment.py tests/intelligence/test_synthesis.py tests/intelligence/test_golden_dataset.py -q`

Expected: PASS, including unsupported claim rate zero for the Golden Dataset.

- [ ] **Step 8: Commit Task 5**

```powershell
git add app/intelligence/facts.py app/intelligence/assessment.py app/intelligence/synthesis.py tests/intelligence
git commit -m "feat: assess evidence and importance independently"
```

### Task 6: Rank Events and Enforce Daily Brief Publication Gates

**Files:**
- Create: `app/intelligence/briefs.py`
- Create: `app/intelligence/reading_time.py`
- Create: `app/services/daily_brief.py`
- Test: `tests/intelligence/test_reading_time.py`
- Test: `tests/intelligence/test_brief_selection.py`
- Test: `tests/services/test_daily_brief.py`

**Interfaces:**
- Consumes: assessment and synthesis services from Task 5 plus `SourceHealth`.
- Produces: `ReadingTimeEstimator.estimate_seconds(content) -> int`.
- Produces: `DailyBriefService.generate(brief_date, *, now, version) -> DailyBriefResult`.
- Produces statuses `DRAFT`, `PUBLISHED`, `LOW_SIGNAL_DAY`, `DEGRADED_SOURCE_COVERAGE`, and `REJECTED`.

- [ ] **Step 1: Write failing reading-time and selection tests**

Cover Korean-only, Latin-only, mixed content, exactly 300 seconds, 301 seconds, shortening, and lowest-ranked-item removal while maintaining normal minimum three.

- [ ] **Step 2: Write failing coverage and low-signal tests**

```python
def test_healthy_sources_allow_two_item_low_signal_brief(session, healthy_source_health) -> None:
    seed_qualifying_events(session, count=2)
    result = DailyBriefService(session).generate(
        BRIEF_DATE, now=GENERATION_TIME, version="brief-v1"
    )
    assert result.status is BriefStatus.LOW_SIGNAL_DAY
    assert result.item_count == 2


def test_stale_required_source_blocks_publication(session, stale_hn_health) -> None:
    seed_qualifying_events(session, count=6)
    result = DailyBriefService(session).generate(
        BRIEF_DATE, now=GENERATION_TIME, version="brief-v1"
    )
    assert result.status is BriefStatus.DEGRADED_SOURCE_COVERAGE
    assert result.published_at is None
```

- [ ] **Step 3: Write failing late-arrival and provenance snapshot tests**

Test current-window inclusion before cutoff, post-publication evidence enrichment without silent mutation, next-window suppression of an already briefed event, material follow-up as a new event, and old backfill exclusion. Assert every `BriefItemFact` references both the exact fact and evidence used.

- [ ] **Step 4: Run focused tests and verify failure**

Run: `.venv/Scripts/python -m pytest tests/intelligence/test_reading_time.py tests/intelligence/test_brief_selection.py tests/services/test_daily_brief.py -q`

Expected: FAIL because brief services are absent.

- [ ] **Step 5: Implement ranking, source coverage, late-arrival, and count gates**

Rank only `SUPPORTED`/`STRONG` events by importance, then confidence, recency, and stable event ID. Verify every required source has a successful covered interval for the window before classifying low signal. Create a new brief version on correction; never mutate a published version.

- [ ] **Step 6: Implement the 300-second publication gate**

Estimate from final rendered fields, shorten bounded narrative fields first, then remove the lowest-ranked event. Publish one or two items only for healthy low-signal days. A normal brief that cannot stay within 300 seconds with at least three items becomes `REJECTED`.

- [ ] **Step 7: Run focused, Golden, and replay-determinism tests**

Run: `.venv/Scripts/python -m pytest tests/intelligence tests/services/test_daily_brief.py tests/services/test_replay.py -q`

Expected: PASS; Golden incorrect merges and unsupported claims remain zero, and repeated generation with the same versions is stable.

- [ ] **Step 8: Commit Task 6**

```powershell
git add app/intelligence/briefs.py app/intelligence/reading_time.py app/services/daily_brief.py tests/intelligence tests/services/test_daily_brief.py
git commit -m "feat: generate gated daily intelligence briefs"
```

### Task 7: Expose Today API and Schedule the Daily Pipeline

**Files:**
- Create: `app/api/today.py`
- Create: `app/services/intelligence_scheduler.py`
- Create: `scripts/run_intelligence_pipeline.py`
- Modify: `app/main.py`
- Modify: `app/services/scheduler.py`
- Test: `tests/api/test_today.py`
- Test: `tests/services/test_intelligence_scheduler.py`
- Test: `tests/services/test_intelligence_pipeline.py`

**Interfaces:**
- Consumes: `IntelligenceCollectionService`, `EventProcessingService`, and `DailyBriefService`.
- Produces: `GET /api/public/today` and `GET /api/public/briefs/{brief_date}` for published/low-signal responses only.
- Produces: scheduler jobs for 15-minute collection and processing, a 07:30 cutoff followed by 07:35 ranking/generation, and 08:00 publication in `Asia/Seoul`.

- [ ] **Step 1: Write failing public API tests**

Assert published response shape, low-signal messaging, real statistics, ordered source links, FACT provenance IDs kept internal, dated brief lookup, 404 for absent dates, and no exposure of drafts/rejected/degraded briefs.

- [ ] **Step 2: Write failing scheduler and orchestration tests**

Assert stable job IDs, `coalesce=True`, `max_instances=1`, Seoul timezone, per-source failure isolation, idempotent run keys, and blocked publication under degraded coverage.

- [ ] **Step 3: Run focused tests and verify failure**

Run: `.venv/Scripts/python -m pytest tests/api/test_today.py tests/services/test_intelligence_scheduler.py tests/services/test_intelligence_pipeline.py -q`

Expected: FAIL because routes and orchestration are absent.

- [ ] **Step 4: Implement API serializers without BriefItem save endpoints**

Return `briefDate`, `status`, `todayInOneLine`, `readingTimeSeconds`, actual counts, and items with headline/category/what happened/why it matters/fact/interpretation/watch/sources. Do not add save or feedback endpoints for BriefItems.

- [ ] **Step 5: Implement scheduler and CLI orchestration**

Keep existing scheduler jobs and add separate intelligence jobs. The CLI supports `--collect`, `--process`, `--brief-date YYYY-MM-DD`, and `--dry-run`; dry-run may fetch/parse fixtures or live GET data but does not publish.

- [ ] **Step 6: Run API, scheduler, and existing public API tests**

Run: `.venv/Scripts/python -m pytest tests/api tests/services/test_scheduler.py tests/services/test_intelligence_scheduler.py tests/services/test_intelligence_pipeline.py -q`

Expected: PASS with existing feed/saved/settings behavior intact.

- [ ] **Step 7: Commit Task 7**

```powershell
git add app/api/today.py app/main.py app/services/intelligence_scheduler.py app/services/scheduler.py scripts/run_intelligence_pipeline.py tests/api tests/services
git commit -m "feat: expose and schedule daily intelligence briefs"
```

### Task 8: Build the SoloPilot Today UI While Preserving Saved

**Files:**
- Create: `frontend/src/pages/Today.tsx`
- Create: `frontend/src/components/BriefItem.tsx`
- Create: `frontend/src/pages/Today.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/index.html`
- Modify: `app/main.py`
- Test: `frontend/src/pages/UserFlows.test.tsx`

**Interfaces:**
- Consumes: `GET /api/public/today` from Task 7.
- Produces: `/today` as default, `/radar` as the renamed existing Explore surface without new inference, and unchanged `/saved`/`/settings` routes.

- [ ] **Step 1: Write failing Today UI tests**

```tsx
test('renders an evidence-grounded brief without save controls', async () => {
  render(<App />)
  expect(await screen.findByRole('heading', { name: '오늘의 IT 5분' })).toBeInTheDocument()
  expect(screen.getByText('FACT')).toBeInTheDocument()
  expect(screen.getByText('INTERPRETATION')).toBeInTheDocument()
  expect(screen.getByText('WATCH')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /저장/ })).not.toBeInTheDocument()
})
```

Also cover low-signal messaging, source links, actual statistics, reading time, degraded/absent brief error state, and `/saved` continuing to render existing Trend cards.

- [ ] **Step 2: Run frontend tests and verify failure**

Run: `cd frontend; npm test -- --run`

Expected: FAIL because Today types, API, route, and components are missing.

- [ ] **Step 3: Add typed API contract and Today components**

Add `TodayBrief`, `DailyBriefItem`, and `BriefSource` interfaces. Render editorial hierarchy with the top event emphasized, no infinite scroll, accessible external-source names, distinct FACT/INTERPRETATION/WATCH labels, and real analysis statistics.

- [ ] **Step 4: Change user-facing branding and navigation only**

Set title/visible brand to SoloPilot, root redirect to `/today`, and bottom nav to Today/Radar/Saved/Settings. Do not rename npm package, Python project, database, internal modules, or repository.

- [ ] **Step 5: Run frontend tests, typecheck, lint, and build**

Run: `cd frontend; npm test -- --run; npm run typecheck; npm run lint; npm run build`

Expected: all commands PASS.

- [ ] **Step 6: Commit Task 8**

```powershell
git add frontend app/main.py
git commit -m "feat: add SoloPilot Today experience"
```

### Task 9: Validate the Real-Data Vertical Slice and Quality Gates

**Files:**
- Create: `docs/it-intelligence/source-policy.md`
- Create: `docs/it-intelligence/quality-evaluation.md`
- Create: `docs/it-intelligence/implementation-progress.md`
- Create: `tests/e2e/test_intelligence_vertical_slice.py`
- Modify: `README.md`
- Modify: `.env.example`

**Interfaces:**
- Consumes: the complete pipeline and all five live source adapters.
- Produces: a reproducible real-data validation command, persisted quality report, and explicit limitations.

- [ ] **Step 1: Write a failing database-backed vertical-slice test**

Use recorded real HTTP payload fixtures through the same collector parsers and persistence services. Assert `RawFetch → RawItem → EventCluster → EventEvidence/EventFact → EventAssessment → BriefItem → Today response`, no duplicate event cards, no unsupported fact, source-link preservation, item-count semantics, and reading time at or below 300 seconds.

- [ ] **Step 2: Run the vertical-slice test and verify failure before final wiring**

Run: `.venv/Scripts/python -m pytest tests/e2e/test_intelligence_vertical_slice.py -q`

Expected: FAIL until every production stage is connected.

- [ ] **Step 3: Wire only the missing production path revealed by the E2E failure**

Keep fixes within the owning service boundaries. Do not add alternate fixture-only orchestration or bypass publication gates.

- [ ] **Step 4: Run a live GET-only collection and dry-run brief against the five enabled sources**

Run: `.venv/Scripts/python scripts/run_intelligence_pipeline.py --collect --process --brief-date 2026-09-23 --dry-run`

Expected: each source records success or an explicit health failure; the command never fabricates coverage. If a provider is unavailable, preserve the failure evidence and validate that publication becomes `DEGRADED_SOURCE_COVERAGE`.

- [ ] **Step 5: Record actual quality metrics**

Document Golden Dataset size, Incorrect Merge count/rate, Duplicate Escape count/rate, Unclustered Rate, Unsupported Claim Rate, selected item count, source coverage, and reading time from test and real-data outputs. No placeholder or invented metric is permitted.

- [ ] **Step 6: Run proportional regression and release verification**

Run:

```powershell
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m pytest -q
Push-Location frontend
npm test -- --run
npm run typecheck
npm run lint
npm run build
Pop-Location
git diff --check a229c14..HEAD
```

Expected: all commands PASS; existing skipped integration tests remain explicitly reported.

- [ ] **Step 7: Review the final diff against the spec and commit documentation**

Check for unexpected files, destructive migrations, package/repository renames, BriefItem save functionality, enabled legacy sources, unsupported claims, missing provenance, and untested Hard Negatives.

```powershell
git add README.md .env.example docs/it-intelligence tests/e2e/test_intelligence_vertical_slice.py
git commit -m "docs: record intelligence slice validation"
```
