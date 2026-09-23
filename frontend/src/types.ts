export type DataMode = 'LIVE' | 'DEMO'
export type Category =
  | 'SPORTS'
  | 'ENTERTAINMENT'
  | 'FOOD'
  | 'GAME'
  | 'AI_TECH'
  | 'MEME_INTERNET'
  | 'FASHION_BEAUTY'
  | 'SHOPPING_PRODUCT'

export interface CategoryOption {
  category: Category
  label: string
  status: 'ENABLED' | 'EXPERIMENTAL'
}

export interface CategoriesResponse {
  dataMode: DataMode
  items: CategoryOption[]
}

export type Feedback = 'NEW_AND_USEFUL' | 'ALREADY_KNEW' | 'NOT_INTERESTED' | 'INCORRECT'

export interface TrendItem {
  trendId: string
  title: string
  category: Category
  lifecycle: 'NEW' | 'RISING' | 'HOT' | 'COOLING'
  summary: string
  firstSeenAt: string
  observedAt: string
  sourceNames: string[]
  saved: boolean
  feedback: Feedback | null
  rankingReasons: string[]
  dataMode: DataMode
}

export interface TrendDetail extends TrendItem {
  what: string
  why: string
  sources: Array<{ source: string; url: string; observedAt: string }>
}

export interface BriefSource {
  title: string
  url: string
}

export interface DailyBriefItem {
  position: number
  headline: string
  category: string
  whatHappened: string
  whyItMatters: string
  fact: string[]
  interpretation: string
  watch: string
  sources: BriefSource[]
  importance: number
}

export interface TodayBrief {
  briefDate: string
  status: 'PUBLISHED' | 'LOW_SIGNAL_DAY'
  todayInOneLine: string | null
  readingTimeSeconds: number
  emptyStateMessage: string | null
  statistics: {
    rawItemCount: number
    eventClusterCount: number
    candidateCount: number
    selectedCount: number
  }
  items: DailyBriefItem[]
}
