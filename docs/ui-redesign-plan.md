# Mobile-first User MVP UI Redesign Plan

## Current problems

- The 680px document layout, oversized editorial headings, and text-only three-tab navigation feel
  like a responsive website rather than a mobile app.
- The warm beige/green visual language is coherent but too reserved for a 20–30s consumer trend app.
- Cards are visually uniform; category and lifecycle signals do not create enough scanning rhythm.
- Interest choices still read as styled checkboxes, while loading, save confirmation, and transitions
  lack polished feedback.
- Detail and settings pages use generic bordered sections instead of app-native editorial/grouped
  patterns. Explore is absent even though the desired navigation includes it.

## Design direction

Use **Soft Signal Editorial**: a centered `max-width: 520px` app shell on `#F7F7FA`, restrained
Electric Violet accents, category-specific single accents, compact editorial typography, and subtle
motion. The trend title remains the strongest card element. No photos are required; category glyphs,
soft glows, and simple geometry provide visual distinction without licensing risk.

## Flows and screens

- Onboarding: custom radar mark, benefit-led headline, expressive category tiles, persistent CTA.
- Home: friendly header, horizontal interest filters, skeleton/empty/error states, scan-first cards.
- Explore: real feed-derived category browsing only; no fake search or new backend endpoint.
- Detail: app bar, lifecycle/title/summary hero, readable what/why/evidence sections, feedback and save.
- Saved: compact saved-card list with honest empty state.
- Settings: grouped interest and notification preferences with a clear saved state.
- Global: Home/Explore/Saved/Settings bottom navigation, DEMO ribbon, safe-area padding, toast region.

## Components

- `BrandMark`, `AppIcon`, `TopBar`, `BottomNav`, `CategoryChip`, `InterestTile`
- `LifecycleBadge`, `TrendCard`, `FeedbackBar`, `SourceList`
- `SkeletonCard`, `EmptyState`, `Toast`

Existing API response types and mutations remain unchanged. Explore filters the already-fetched feed
client-side and does not manufacture unavailable data.

## External resources

- Pretendard Variable for Korean typography.
- Lucide React for interface icons; the brand mark remains a custom inline SVG.
- No photography, external illustration, UI kit, Tailwind, state library, or motion library.
- Record exact versions, official sources, licenses, commercial-use status, and attribution in
  `THIRD_PARTY_LICENSES.md` before final verification.

## Implementation order

1. Foundation: tokens, font/icon dependencies, app shell, navigation, primitives, base tests.
2. Onboarding and feed: interest tiles, home header/filter chips, lifecycle/card hierarchy, states.
3. Detail and secondary screens: editorial detail, Explore, Saved, grouped Settings.
4. Interaction polish: feedback/save states, toast, motion, safe areas, responsive wrapping.
5. Visual QA: 390×844 and 430×932 screenshots, accessibility checks, final tests/build/review.

## Acceptance criteria

- The UI reads as a consumer mobile app at 360, 375, 390, and 430px and remains centered on desktop.
- Trend names dominate card hierarchy; lifecycle always uses icon + text + color.
- All interactive controls have visible focus and at least 44×44px targets; reduced motion is honored.
- Loading uses skeletons, empty/error states are explicit, and save/feedback actions visibly confirm.
- DEMO remains visibly labelled and never appears as LIVE; no backend gate or API contract changes.
- No internal score, enum, raw provenance field, or technical configuration appears in user UI.
- Frontend tests, lint, typecheck, production build, screenshot review, and final independent review pass.

## Completion record

- Implemented the mobile shell and all planned screens without backend or publish-gate changes.
- Verified the four required flows with isolated DEMO fixtures; DEMO labels remained visible and no
  internal source enum appeared in the rendered UI.
- Reviewed 390×844 and 430×932 screenshots, plus 375×667 onboarding and 360px overflow/touch metrics.
- Final frontend verification: 13 tests passed, TypeScript, ESLint, production build, and diff check.
- Independent final review: Critical 0, High 0, Ready Yes.
