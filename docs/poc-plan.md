# AI Personal Trend Radar — Data PoC Plan

## Goal

공식적으로 이용 가능한 데이터만 사용해 한국 사용자를 위한 Personal Trend Radar가 지속적으로 유효한 Trend Card를 만들 수 있는지 측정한다. 14~28일 운영을 전제로 수집량, 카테고리별 공급량, 중복·노이즈, 탐지 지연, 근거 품질, 비용을 재현 가능한 방식으로 기록한다.

## Non-goals

- 소비자용 모바일/웹 앱, 회원가입, OAuth, 결제, 광고, 소셜/커뮤니티 기능
- 미래 유행 확률, 추천 ML 모델, 자동 매매·쇼핑
- 비공식 API, scraping, reverse-engineered/private endpoint
- Meta 승인 전 Instagram/Threads 실호출
- Kafka, Kubernetes, Elasticsearch, Redis Cluster, CQRS, Event Sourcing, microservices

## Confirmed data sources

1. **Google Trends Trending Now RSS**
   - Endpoint: `https://trends.google.com/trending/rss?geo=KR`
   - 2026-09-20 preflight에서 HTTP 200 및 RSS XML 응답 확인
   - title, publication timestamp, approximate traffic, related news metadata처럼 feed가 실제 제공하는 값만 저장
   - Google Trends attribution과 source URL 유지
   - Google Trends API alpha는 제한된 테스터만 접근 가능하므로 자격 증명 없이는 비활성
2. **Wikimedia Analytics API**
   - Endpoint pattern: `https://wikimedia.org/api/rest_v1/metrics/pageviews/top-per-country/KR/all-access/{year}/{month}/{day}`
   - 2026-09-20 preflight에서 최근 날짜 응답과 `country`, `project`, `article`, `views_ceil`, `rank` 확인
   - CC0, 식별 가능한 User-Agent, 순차 호출, 서버의 throttling/backoff 지시 준수
3. **Wikidata Wikibase API**
   - Endpoint: `https://www.wikidata.org/w/api.php`
   - `wbsearchentities`와 `wbgetentities`만 사용해 label, alias, description, entity id를 조회
   - 모호한 결과는 자동 병합하지 않고 `NEEDS_REVIEW` 처리

## Forbidden data sources

NAVER Search/DataLab, TikTok, Reddit, X, YouTube 결합 점수, Instagram/Threads scraping, 비공식 Google Trends client(pytrends 포함), 브라우저 scraping, 로그인 세션·private endpoint·reverse-engineered API는 사용하지 않는다. 새 source가 필요하지만 권한이 불명확하면 `BLOCKED_SOURCE` 형식으로만 기록한다.

## Architecture

- Python 3.12 modular monolith
- FastAPI + server-rendered Jinja dashboard
- SQLAlchemy 2 + Alembic + PostgreSQL 16; 단위 테스트는 SQLite를 사용하고 PostgreSQL 통합 smoke test를 별도로 수행
- httpx 기반 allowlisted outbound client, bounded timeout, bounded response size, retry/backoff
- APScheduler 기반 단일 프로세스 scheduler; 수집/파이프라인/리포트 작업은 독립 CLI로도 실행
- 모든 파이프라인 함수는 `as_of`를 받아 replay/backtest에서 미래 데이터 접근을 막음
- AI 설명 계층은 provider protocol로 분리한다. 운영 기본값은 evidence-only deterministic summary이며, 테스트에서는 가짜 LLM provider로 unsupported claim 차단을 검증한다. 실제 LLM은 credential과 정책이 명시되기 전 비활성이다.

## Database model

- `collection_runs`: source별 수집 실행, 시작/종료/상태/오류
- `raw_payloads`: hash로 중복 제거된 원본 응답, parser/collector version, source timestamp
- `source_observations`: 실행별 source item과 실제 제공 metric; 동일 payload 재사용 시에도 시계열 관측 유지
- `trend_candidates`, `candidate_observations`: 규칙 기반 후보와 raw provenance
- `trend_entities`, `entity_aliases`, `entity_candidates`: canonical entity, Wikidata id, alias 및 병합 상태
- `entity_classifications`: category/confidence/reason/classifier version 이력
- `trend_snapshots`: `as_of`별 lifecycle, score, breakdown, score version
- `evidence`, `claims`, `claim_evidence`: 공개 문장과 근거 및 support 상태
- `reviews`, `human_evaluations`: 검수 액션과 평가 label
- `cost_records`, `pipeline_runs`: 비용과 재현성 version metadata

모든 시간은 UTC로 저장하고 API/리포트에서 필요할 때 Asia/Seoul로 표시한다. JSON 원본은 data로만 취급하며 실행 지시로 해석하지 않는다.

## Pipeline

1. Google/Wikimedia 공식 endpoint 수집
2. raw payload hash 저장 + 실행별 source observation 저장
3. 결정적 candidate 생성 및 문자열 NFKC 정규화
4. exact alias와 Wikidata 후보로 entity 연결; 모호하면 `NEEDS_REVIEW`
5. 규칙/Wikidata metadata 기반 분류, 미결정은 `OTHER`
6. 시간 창별 velocity/novelty/persistence/cross-source와 baseline/repetition/news-only penalty 계산
7. `NEW`, `RISING`, `HOT`, `COOLING` lifecycle snapshot 생성
8. 상위 후보에만 evidence-grounded summary 생성 및 claim 검증
9. 내부 dashboard 검수와 human evaluation 기록
10. daily/weekly evaluation report 및 replay/backtest 실행

## Evaluation metrics

- Supply: raw candidates, unique candidates, entities, approved cards
- Coverage: category별 candidates/day, valid cards/day
- Quality: duplicate, noise, merge error, classification error, unsupported summary rate
- Freshness: first source seen → system detected → approved
- Cost: API/LLM/compute/human minutes, cost per approved card
- Human labels: VALID_TREND, TOO_OBVIOUS, NEWS_ONLY, DUPLICATE, WRONG_CATEGORY, BAD_ENTITY_MERGE, NOT_USEFUL, INSUFFICIENT_EVIDENCE

분모가 0인 비율은 0으로 위조하지 않고 `null`/`N/A`로 보고한다. Trend Score는 내부 상대 점수이며 확률로 표현하지 않는다.

## Known risks

- Google Trending Now RSS는 검색 관심 후보 발견에는 적합하지만 API alpha처럼 일관된 장기 시계열을 제공하지 않는다.
- RSS가 제공하는 `approx_traffic`은 구간형 근사치이며 정확한 검색 횟수가 아니다.
- Wikimedia `views_ceil`은 반올림된 상한값이고, 메인 페이지·검색·방송사 등 상시 항목이 강한 baseline noise를 만든다.
- 공식 두 source만으로 FOOD, MEME_INTERNET, FASHION_BEAUTY, SHOPPING_PRODUCT 공급량이 부족할 수 있다.
- 단순 뉴스 급상승과 문화적 관심 증가는 source만으로 완전 분리할 수 없어 human evaluation이 필요하다.
- Wikidata label/alias만으로 동명이인을 확정할 수 없으며 자동 병합 임계값을 보수적으로 유지해야 한다.
- Meta 승인과 공식 권한이 없으므로 Meta 검증은 disabled provider만 제공한다.

## Implementation phases

1. Foundation: Python/Docker/config/schema/migrations/test harness
2. Collection: Google RSS, Wikimedia, raw persistence, idempotency/retry
3. Candidate/entity: deterministic candidates, normalization, Wikidata resolution
4. Classification/trend: enum category, baseline/noise, lifecycle and explainable score
5. Evidence/summary: claim-evidence model, checker, disabled Meta and LLM providers
6. Review: FastAPI/Jinja dashboard and review actions
7. Evaluation: daily/weekly metrics and Markdown reports
8. Operations: scheduler, replay, leakage-safe backtest, end-to-end verification and README
