import { useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { Bookmark, BookmarkCheck } from 'lucide-react'

import { api } from '../api'
import type { TrendItem } from '../types'
import FeedbackBar from './FeedbackBar'
import LifecycleBadge from './LifecycleBadge'

const categoryLabels: Record<string, string> = {
  SPORTS: '스포츠', ENTERTAINMENT: '엔터', FOOD: '음식', GAME: '게임',
  AI_TECH: 'AI / IT', MEME_INTERNET: '인터넷 문화', FASHION_BEAUTY: '패션 / 뷰티',
  SHOPPING_PRODUCT: '쇼핑 / 제품',
}

function freshness(value: string) {
  const hours = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 3_600_000))
  if (hours < 1) return '방금 전'
  if (hours < 24) return `${hours}시간 전`
  return `${Math.floor(hours / 24)}일 전`
}

export default function TrendCard({ item, compact = false, onSavedChange }: { item: TrendItem; compact?: boolean; onSavedChange?: (saved: boolean) => void }) {
  const [saved, setSaved] = useState(item.saved)
  const [saveBusy, setSaveBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const observed = useRef(false)
  const root = useRef<HTMLElement>(null)
  const location = useLocation()

  useEffect(() => {
    if (!notice) return
    const timer = window.setTimeout(() => setNotice(''), 2200)
    return () => window.clearTimeout(timer)
  }, [notice])

  useEffect(() => {
    const record = () => {
      if (observed.current) return
      observed.current = true
      void api.event('TREND_IMPRESSION', item.trendId).catch(() => undefined)
    }
    if (!('IntersectionObserver' in window) || !root.current) {
      record()
      return
    }
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) record()
    }, { threshold: 0.5 })
    observer.observe(root.current)
    return () => observer.disconnect()
  }, [item.trendId])

  async function toggleSave() {
    setSaveBusy(true)
    try {
      if (saved) await api.unsave(item.trendId)
      else await api.save(item.trendId)
      const nextSaved = !saved
      setSaved(nextSaved)
      onSavedChange?.(nextSaved)
      setNotice(saved ? '저장을 취소했어요' : '저장했어요')
    } finally {
      setSaveBusy(false)
    }
  }

  return (
    <article className={`trend-card${compact ? ' trend-card-compact' : ''}`} data-category={item.category} ref={root}>
      <span className="card-glow" aria-hidden="true" />
      <div className="card-topline">
        <LifecycleBadge lifecycle={item.lifecycle} />
        <button className="save-button" aria-label={saved ? '저장 취소' : '저장'} aria-pressed={saved} disabled={saveBusy} onClick={() => void toggleSave()}>
          {saved ? <BookmarkCheck aria-hidden="true" size={20} /> : <Bookmark aria-hidden="true" size={20} />}
        </button>
      </div>
      <Link className="card-link" state={{ from: location.pathname }} to={`/trends/${item.trendId}`}>
        <h2>{item.title}</h2>
        <p>{item.summary}</p>
      </Link>
      <div className="meta-row">
        <span>{categoryLabels[item.category]}</span><span aria-hidden="true">·</span>
        <time dateTime={item.observedAt}>{freshness(item.observedAt)}</time>
      </div>
      {!compact && <FeedbackBar trendId={item.trendId} initial={item.feedback} />}
      {notice && <span className="toast" role="status">{notice}</span>}
    </article>
  )
}
