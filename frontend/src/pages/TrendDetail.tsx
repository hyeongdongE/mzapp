import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { api } from '../api'
import FeedbackBar from '../components/FeedbackBar'
import LifecycleBadge from '../components/LifecycleBadge'
import SourceList from '../components/SourceList'
import type { TrendDetail as Detail } from '../types'

export default function TrendDetail() {
  const { id = '' } = useParams()
  const [detail, setDetail] = useState<Detail | null>(null)
  const [reported, setReported] = useState(false)
  useEffect(() => { void api.trend(id).then(setDetail) }, [id])
  if (!detail) return <main className="state-page" aria-live="polite">근거를 확인하는 중…</main>

  return (
    <main className="page detail-page">
      <Link className="back-link" to="/feed">← 피드</Link>
      <LifecycleBadge lifecycle={detail.lifecycle} />
      <h1>{detail.title}</h1>
      <section><h2>이게 뭔데?</h2><p>{detail.what}</p></section>
      <section><h2>왜 관심이 늘고 있나요?</h2><p>{detail.why}</p></section>
      <section><h2>어디서 확인됐나요?</h2><SourceList sources={detail.sources} /></section>
      <FeedbackBar trendId={detail.trendId} initial={detail.feedback} />
      <button className="report-button" disabled={reported} onClick={() => {
        void api.feedback(detail.trendId, 'INCORRECT').then(() => setReported(true))
      }}>{reported ? '의견을 남겼어요' : '내용이 부정확해요'}</button>
    </main>
  )
}
