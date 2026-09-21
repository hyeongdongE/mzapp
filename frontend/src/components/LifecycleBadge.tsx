import { Flame, Sparkles, TrendingDown, TrendingUp } from 'lucide-react'

const labels = {
  NEW: '새롭게 발견',
  RISING: '관심 상승 중',
  HOT: '높은 관심 유지',
  COOLING: '관심 감소 중',
} as const

const icons = { NEW: Sparkles, RISING: TrendingUp, HOT: Flame, COOLING: TrendingDown } as const

export default function LifecycleBadge({ lifecycle }: { lifecycle: keyof typeof labels }) {
  const Icon = icons[lifecycle]
  return <span className={`lifecycle lifecycle-${lifecycle.toLowerCase()}`}><Icon aria-hidden="true" size={15} strokeWidth={2.5} />{labels[lifecycle]}</span>
}
