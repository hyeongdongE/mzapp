const labels = {
  NEW: '새롭게 발견',
  RISING: '관심 상승 중',
  HOT: '높은 관심 유지',
  COOLING: '관심 감소 중',
} as const

export default function LifecycleBadge({ lifecycle }: { lifecycle: keyof typeof labels }) {
  return <span className={`lifecycle lifecycle-${lifecycle.toLowerCase()}`}>{labels[lifecycle]}</span>
}
