import { useEffect, useState } from 'react'

import { api } from '../api'
import TrendCard from '../components/TrendCard'
import type { TrendItem } from '../types'

export default function Saved() {
  const [items, setItems] = useState<TrendItem[] | null>(null)
  useEffect(() => { void api.saved().then((result) => setItems(result.items)) }, [])
  return (
    <main className="page saved-page">
      <header className="page-header compact-header"><p className="eyebrow">BOOKMARKS</p><h1>저장한 트렌드</h1><p className="lede">나중에 다시 보고 싶은 흐름을 모았어요.</p></header>
      {items === null && <section className="card-list" aria-label="저장한 트렌드를 불러오는 중"><div className="trend-skeleton" /></section>}
      {items?.length === 0 && <section className="empty-panel feed-empty"><span className="empty-symbol" aria-hidden="true">♡</span><h2>아직 저장한 트렌드가 없어요</h2><p>다시 보고 싶은 흐름에 북마크를 눌러보세요.</p></section>}
      <section className="card-list">{items?.map((item) => <TrendCard compact item={item} key={item.trendId} onSavedChange={(saved) => {
        if (!saved) setItems((current) => current?.filter((candidate) => candidate.trendId !== item.trendId) ?? [])
      }} />)}</section>
    </main>
  )
}
