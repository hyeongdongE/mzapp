import { useEffect, useMemo, useState } from 'react'

import { api } from '../api'
import TrendCard from '../components/TrendCard'
import { useAppState } from '../App'
import type { Category, TrendItem } from '../types'

export default function Explore() {
  const { catalog } = useAppState()
  const [items, setItems] = useState<TrendItem[] | null>(null)
  const [category, setCategory] = useState<Category | 'ALL'>('ALL')

  useEffect(() => {
    void api.feed().then((result) => setItems(result.items)).catch(() => setItems([]))
  }, [])

  const visibleItems = useMemo(
    () => items?.filter((item) => category === 'ALL' || item.category === category),
    [category, items],
  )

  return (
    <main className="page explore-page">
      <header className="page-header compact-header">
        <p className="eyebrow">DISCOVER</p>
        <h1>요즘 뜨는 분야</h1>
        <p className="lede">관심이 올라온 흐름을 분야별로 가볍게 둘러보세요.</p>
      </header>
      <div className="chip-row" aria-label="분야 선택">
        <button aria-pressed={category === 'ALL'} onClick={() => setCategory('ALL')}>전체</button>
        {catalog.items.map((item) => (
          <button
            aria-pressed={category === item.category}
            key={item.category}
            onClick={() => setCategory(item.category)}
          >
            {item.label}
          </button>
        ))}
      </div>
      {items === null && <p className="loading-line" aria-live="polite">새로운 흐름을 확인하는 중…</p>}
      {visibleItems?.length === 0 && (
        <section className="empty-panel">
          <span className="empty-symbol" aria-hidden="true">◌</span>
          <h2>아직 새로운 흐름이 없어요</h2>
          <p>의미 있는 변화가 보이면 여기에 표시돼요.</p>
        </section>
      )}
      <section className="card-list" aria-label="최근 관심이 올라온 흐름">
        {visibleItems?.map((item) => <TrendCard item={item} key={item.trendId} />)}
      </section>
    </main>
  )
}
