import { useEffect, useState } from 'react'

import { api } from '../api'
import TrendCard from '../components/TrendCard'
import type { TrendItem } from '../types'

export default function Feed() {
  const [items, setItems] = useState<TrendItem[] | null>(null)
  const [error, setError] = useState(false)
  useEffect(() => { void api.feed().then((result) => setItems(result.items)).catch(() => setError(true)) }, [])

  return (
    <main className="page feed-page">
      <header className="page-header"><p className="eyebrow">YOUR RADAR</p><h1>놓친 변화만<br />빠르게.</h1></header>
      {error && <section className="empty-panel"><h2>피드를 불러오지 못했습니다</h2><button onClick={() => window.location.reload()}>다시 시도</button></section>}
      {items === null && !error && <p className="loading-line" aria-live="polite">새로운 흐름을 확인하는 중…</p>}
      {items?.length === 0 && <section className="empty-panel"><h2>오늘은 아직 새로운 변화가 없습니다.</h2><p>의미 있는 관심 증가가 감지되면 여기에 표시됩니다.</p></section>}
      <section className="card-list">{items?.map((item) => <TrendCard item={item} key={item.trendId} />)}</section>
    </main>
  )
}
