import { useEffect, useMemo, useState } from 'react'
import { Settings } from 'lucide-react'
import { Link } from 'react-router-dom'

import { api } from '../api'
import { useAppState } from '../App'
import TrendCard from '../components/TrendCard'
import type { Category, TrendItem } from '../types'

export default function Feed() {
  const { catalog, interests } = useAppState()
  const [items, setItems] = useState<TrendItem[] | null>(null)
  const [error, setError] = useState(false)
  const [category, setCategory] = useState<Category | 'ALL'>('ALL')
  useEffect(() => { void api.feed().then((result) => setItems(result.items)).catch(() => setError(true)) }, [])

  const filters = catalog.items.filter((item) => interests.length === 0 || interests.includes(item.category))
  const visibleItems = useMemo(
    () => items?.filter((item) => category === 'ALL' || item.category === category),
    [category, items],
  )

  return (
    <main className="page feed-page">
      <header className="home-header">
        <div>
          <p className="greeting">오늘 뭐가 뜨고 있을까?</p>
          <h1>{items?.length ? <>놓치면 아쉬운<br /><span>새로운 흐름 {items.length}개</span></> : '새로운 흐름을 찾고 있어요'}</h1>
        </div>
        <Link className="icon-button" aria-label="설정 열기" to="/settings"><Settings aria-hidden="true" size={21} /></Link>
      </header>
      <div className="chip-row feed-filters" aria-label="관심 분야 필터">
        <button aria-pressed={category === 'ALL'} onClick={() => setCategory('ALL')}>전체</button>
        {filters.map((item) => (
          <button aria-pressed={category === item.category} key={item.category} onClick={() => setCategory(item.category)}>{item.label}</button>
        ))}
      </div>
      {error && <section className="empty-panel"><h2>피드를 불러오지 못했습니다</h2><button onClick={() => window.location.reload()}>다시 시도</button></section>}
      {items === null && !error && <section className="card-list" aria-label="새로운 흐름을 불러오는 중"><div className="trend-skeleton" /><div className="trend-skeleton" /></section>}
      {visibleItems?.length === 0 && <section className="empty-panel feed-empty"><span className="empty-symbol" aria-hidden="true">◌</span><h2>아직 새로운 흐름이 없어요</h2><p>관심 분야에서 의미 있는 변화가<br />보이면 여기에 표시돼요.</p></section>}
      <section className="card-list">{visibleItems?.map((item) => <TrendCard item={item} key={item.trendId} />)}</section>
    </main>
  )
}
