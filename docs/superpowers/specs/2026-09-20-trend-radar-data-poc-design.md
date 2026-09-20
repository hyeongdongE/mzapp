# AI Personal Trend Radar Data PoC Design

## Intent and success

이 프로젝트는 사용자 앱이 아니라 데이터 가능성 검증 장치다. 공식 데이터만으로 한국 사용자를 위한 새롭고 유용한 Trend Card를 하루에 몇 개 만들 수 있는지, 어떤 카테고리가 부족한지, 중복·상시 인기·뉴스성 spike를 얼마나 억제하는지, Meta 없이 가치가 있는지를 측정 가능한 결과로 남긴다.

성공은 기능 개수가 아니라 다음 observable result로 판단한다.

- 공식 Google Trends RSS와 Wikimedia Analytics 데이터를 반복 수집하고 raw provenance를 보존한다.
- 후보 → entity → category → lifecycle → score → claim/evidence 흐름을 같은 raw data로 재실행할 수 있다.
- 검수자가 dashboard에서 판단을 기록하고 daily/weekly report가 품질·공급·지연·비용을 계산한다.
- 14~28일 후 `CONTINUE_DATA_COLLECTION`, `READY_FOR_USER_MVP`, `CATEGORY_SCOPE_REDUCTION`, `NEED_NEW_DATA_SOURCE`, `POC_NOT_VIABLE` 중 하나를 데이터로 제안할 수 있다.

## Chosen approach

PostgreSQL을 system of record로 두는 Python 3.12 modular monolith를 사용한다. 파일/SQLite-only batch보다 검수 액션과 관계형 provenance를 안전하게 보존하고, dataframe/DuckDB 중심 구조보다 FastAPI dashboard 및 장기 scheduler와 자연스럽게 연결된다. 분산 시스템은 도입하지 않는다.

로컬 실행은 Docker Compose가 Python 3.12와 PostgreSQL 16을 제공한다. 개발 호스트의 Python 3.10은 프로젝트 runtime으로 간주하지 않으며, `uv`는 dependency lock과 명령 실행에 사용한다.

## Component boundaries

### Collectors

`GoogleTrendsRssCollector`, `WikimediaTopPagesCollector`, `WikidataClient`는 공통 `SafeHttpClient`만 사용한다. client는 HTTPS host allowlist, timeout, response-size limit, bounded retry/backoff, 식별 가능한 User-Agent를 강제한다. collector는 네트워크 응답을 typed batch로 바꾸지만 후보나 점수를 만들지 않는다.

Google 기본 source는 2026-09-20 실제 200 응답을 확인한 `https://trends.google.com/trending/rss?geo=KR`이다. 제한된 alpha API credential이 없는 상태에서는 alpha provider를 활성화하지 않는다. RSS의 `approx_traffic`은 문자열 원본과 해석 가능한 lower bound를 함께 저장하되 정확한 검색 횟수로 표현하지 않는다.

Wikimedia는 `top-per-country/KR/all-access/{date}`를 사용하고 `views_ceil`이라는 원래 의미를 보존한다. 상시 인기 namespace와 page를 필터/penalty할 수 있도록 전체 top list를 축적한다.

### Storage and provenance

원본 payload와 observation occurrence를 분리한다. 동일 payload bytes는 hash로 한 번만 저장하되, 각 collection run에서 관측한 item은 `source_observations`에 별도로 기록해 시계열을 잃지 않는다. 같은 run 재시도는 `(run_id, source_item_id)`로 멱등 처리한다.

후보, entity, classification, trend snapshot, evidence, claim은 원본 observation까지 추적 가능해야 한다. 결과에는 collector/normalizer/entity/classifier/score/prompt version과 `as_of`가 기록된다.

### Entity and category pipeline

정규화는 Unicode NFKC, case folding, whitespace/안전한 punctuation 정리까지만 결정적으로 수행한다. exact normalized alias는 병합할 수 있지만 fuzzy text만으로 자동 병합하지 않는다. Wikidata 결과가 복수이거나 설명·type이 충돌하면 `NEEDS_REVIEW`다.

분류는 Wikidata type/description과 작은 버전 관리 rule set을 먼저 사용하고, 결정 불가 시 `OTHER`다. LLM은 기본 분류 경로가 아니다.

### Trend state and score

모든 계산은 explicit `as_of`와 이전 observation window만 사용한다.

- `NEW`: 최근 24시간 안에 처음 관측되고 과거 baseline에 없음
- `RISING`: 최근 window의 정규화 신호가 직전 window보다 의미 있게 증가하고 2회 이상 관측
- `HOT`: 높은 상대 score가 3개 이상의 observation window 또는 6시간 이상 유지
- `COOLING`: 과거 `RISING/HOT` 이후 최근 신호가 직전 window의 60% 이하로 하락

Score는 0~100 내부 상대값이다. velocity 30, novelty 25, persistence 20, cross-source 25를 더하고 baseline 10, repetition 5, news-only 5를 뺀 뒤 clamp한다. component는 각각 0~1로 저장한다. 단일 source는 cross-source 보너스를 받지 못하지만 그것만으로 탈락하지 않는다.

### Evidence and summaries

`SummaryProvider`는 structured claim과 evidence id만 반환한다. `EvidenceChecker`는 id 존재, source provenance, claim type별 최소 근거를 검사해 `SUPPORTED`, `PARTIALLY_SUPPORTED`, `UNSUPPORTED`, `CONTRADICTED`를 부여한다. 공개 대상은 `SUPPORTED`와 명시적으로 허용된 `PARTIALLY_SUPPORTED`뿐이다.

운영 기본 provider는 evidence-only deterministic summary다. 원인 근거가 없으면 정확히 “관심 증가는 확인되었지만 증가 원인은 확인되지 않았습니다.”를 사용한다. 실제 LLM과 Meta provider는 credential/승인/정책이 확인되기 전 `DISABLED`이며 전체 pipeline은 이들 없이 정상 동작한다.

### Dashboard and evaluation

Jinja 기반 내부 UI는 Today, Candidate List, Detail, Review action만 제공한다. 로컬 기본 bind는 `127.0.0.1`; public deployment는 범위 밖이다. Review action은 append-only audit record와 target state update를 하나의 transaction으로 저장한다.

Daily evaluation은 supply, category coverage, quality, freshness, cost를 계산한다. 0 denominator는 `N/A`다. Weekly report는 daily facts를 다시 raw에서 계산하지 않고 기간 집계하되 결과에 version과 period를 기록한다.

## Error handling and security

- timeout, 429, transient 5xx는 bounded exponential backoff 후 run failure로 기록한다.
- malformed/oversized payload는 저장·파싱을 중단하고 secret이나 raw body 전체를 log하지 않는다.
- 외부 text는 prompt data delimiter 안에 넣고 instruction으로 해석하지 않는다.
- outbound request는 allowlisted HTTPS endpoint로 제한하고 feed 안 URL은 fetch하지 않는다.
- API key는 environment에서만 읽고 `.env.example`에는 이름과 안전한 기본값만 둔다.
- DB write는 run 단위 transaction으로 처리하며 partial failure가 성공으로 표시되지 않는다.

## Testing and verification

단위 테스트는 fixed clock과 fixture payload를 사용한다. collector 정상/빈/API 오류/timeout/malformed/duplicate, entity alias/동명이인/Wikidata unavailable/ambiguous, classification/OTHER, 네 lifecycle과 baseline penalty, unsupported/missing evidence/no-cause summary, evaluation metric과 비용 집계를 포함한다.

PostgreSQL integration test는 migration up/down/up, collection fixture → pipeline → report, dashboard review transaction을 검증한다. live smoke는 Google RSS, Wikimedia, Wikidata 각 1회만 호출하고 실패 시 unit fixture 결과와 분리해 보고한다. 최종 검증은 `pytest`, migration smoke, replay leakage test, Docker healthcheck, 실제 collector run, daily report 생성을 포함한다.

## Deferred by design

- 실제 LLM 호출과 Meta API 호출
- public dashboard 배포 및 사용자 인증
- user profile/personalization
- 추가 데이터 source
- MVP readiness 결정: 최소 운영 데이터가 쌓이기 전에는 `READY_FOR_USER_MVP`를 선택하지 않는다.
