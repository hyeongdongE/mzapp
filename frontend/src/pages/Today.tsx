import { useEffect, useState } from 'react'

import { api } from '../api'
import BriefItem from '../components/BriefItem'
import type { TodayBrief } from '../types'

function duration(seconds: number) {
  const minutes = Math.floor(seconds / 60)
  const remainder = seconds % 60
  return `${minutes}분 ${remainder}초`
}

export default function Today() {
  const [brief, setBrief] = useState<TodayBrief | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let active = true
    void api.today()
      .then((result) => { if (active) setBrief(result) })
      .catch(() => { if (active) setFailed(true) })
    return () => { active = false }
  }, [])

  if (failed) return (
    <main className="page today-page">
      <section className="empty-panel today-empty">
        <p className="eyebrow">SOLOPILOT · TODAY</p>
        <h1>오늘 브리프를 아직 공개하지 못했습니다</h1>
        <p>근거와 source coverage 검증이 끝난 뒤 공개합니다.</p>
      </section>
    </main>
  )
  if (!brief) return <main className="state-page" aria-live="polite"><span className="radar-dot" />오늘의 근거를 정리하고 있어요.</main>

  const stats = brief.statistics
  return (
    <main className="page today-page">
      <header className="today-header">
        <div className="today-brand"><span>SOLOPILOT</span><time dateTime={brief.briefDate}>{brief.briefDate}</time></div>
        <p className="eyebrow">DAILY IT INTELLIGENCE</p>
        <h1>오늘의 IT 5분</h1>
        <p className="today-summary">{brief.todayInOneLine}</p>
        <div className="today-meta">
          <span>약 5분 이내 · {duration(brief.readingTimeSeconds)}</span>
          <span>원문 {stats.rawItemCount}개 → 사건 {stats.eventClusterCount}개 → 오늘 {stats.selectedCount}개</span>
        </div>
      </header>
      {brief.emptyStateMessage && (
        <section className="empty-panel today-empty"><h2>{brief.emptyStateMessage}</h2><p>약한 신호를 채워 넣지 않았습니다.</p></section>
      )}
      <section className="brief-list" aria-label="오늘의 브리프">
        {brief.items.map((item, index) => <BriefItem item={item} key={`${item.position}-${item.headline}`} lead={index === 0} />)}
      </section>
    </main>
  )
}
