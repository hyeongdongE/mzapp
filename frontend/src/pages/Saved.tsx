import { useEffect, useState } from 'react'

import { api } from '../api'
import TrendCard from '../components/TrendCard'
import type { TrendItem } from '../types'

export default function Saved() {
  const [items, setItems] = useState<TrendItem[] | null>(null)
  useEffect(() => { void api.saved().then((result) => setItems(result.items)) }, [])
  return (
    <main className="page">
      <p className="eyebrow">BOOKMARKS</p><h1>저장한<br />트렌드</h1>
      {items?.length === 0 && <section className="empty-panel"><h2>아직 저장한 트렌드가 없습니다</h2><p>다시 보고 싶은 흐름을 저장해 보세요.</p></section>}
      <section className="card-list">{items?.map((item) => <TrendCard compact item={item} key={item.trendId} />)}</section>
    </main>
  )
}
