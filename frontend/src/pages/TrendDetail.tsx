import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Bookmark, BookmarkCheck, ChevronLeft } from 'lucide-react'

import { api } from '../api'
import FeedbackBar from '../components/FeedbackBar'
import LifecycleBadge from '../components/LifecycleBadge'
import SourceList from '../components/SourceList'
import type { TrendDetail as Detail } from '../types'

export default function TrendDetail() {
  const { id = '' } = useParams()
  const [detail, setDetail] = useState<Detail | null>(null)
  const [reported, setReported] = useState(false)
  const [saved, setSaved] = useState(false)
  const [notice, setNotice] = useState('')
  useEffect(() => { void api.trend(id).then((result) => { setDetail(result); setSaved(result.saved) }) }, [id])
  if (!detail) return <main className="state-page" aria-live="polite">근거를 확인하는 중…</main>

  async function toggleSave(current: Detail) {
    if (saved) await api.unsave(current.trendId)
    else await api.save(current.trendId)
    setSaved(!saved)
    setNotice(saved ? '저장을 취소했어요' : '저장했어요')
  }

  return (
    <main className="page detail-page">
      <div className="detail-topbar">
        <Link className="back-link" aria-label="피드로 돌아가기" to="/feed"><ChevronLeft aria-hidden="true" size={24} /></Link>
        <button className="save-button" aria-label={saved ? '저장 취소' : '저장'} aria-pressed={saved} onClick={() => void toggleSave(detail)}>
          {saved ? <BookmarkCheck aria-hidden="true" size={20} /> : <Bookmark aria-hidden="true" size={20} />}
        </button>
      </div>
      <header className="detail-hero">
        <LifecycleBadge lifecycle={detail.lifecycle} />
        <h1>{detail.title}</h1>
        <p>{detail.summary}</p>
      </header>
      <section className="editorial-section"><h2>이게 뭔데?</h2><p>{detail.what}</p></section>
      <section className="editorial-section"><h2>왜 뜨고 있어?</h2><p>{detail.why}</p></section>
      <section className="editorial-section evidence-section"><h2>어디서 확인됐어?</h2><SourceList sources={detail.sources} /></section>
      <FeedbackBar trendId={detail.trendId} initial={detail.feedback} />
      <button className="report-button" disabled={reported} onClick={() => {
        void api.feedback(detail.trendId, 'INCORRECT').then(() => setReported(true))
      }}>{reported ? '의견을 남겼어요' : '내용이 부정확해요'}</button>
      {notice && <span className="toast" role="status">{notice}</span>}
    </main>
  )
}
