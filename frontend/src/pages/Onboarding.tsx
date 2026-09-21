import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { api } from '../api'
import { useAppState } from '../App'
import type { Category } from '../types'

export default function Onboarding() {
  const { catalog, interests, setInterests } = useAppState()
  const [selected, setSelected] = useState<Category[]>(interests)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()

  useEffect(() => { void api.event('ONBOARDING_STARTED').catch(() => undefined) }, [])

  function toggle(category: Category) {
    setSelected((current) => current.includes(category)
      ? current.filter((item) => item !== category)
      : [...current, category])
  }

  async function submit() {
    if (!selected.length) return
    setSaving(true)
    setError(null)
    try {
      const result = await api.updateInterests(selected)
      setInterests(result.categories)
      navigate('/feed')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '저장하지 못했습니다.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <main className="onboarding page">
      <p className="eyebrow">PERSONAL TREND RADAR</p>
      <h1>어떤 변화가<br />궁금하세요?</h1>
      <p className="lede">관심 분야를 고르면 새롭게 떠오르는 흐름만 짧고 근거 있게 보여드려요.</p>
      {catalog.items.length ? (
        <fieldset className="interest-grid">
          <legend className="sr-only">관심 분야</legend>
          {catalog.items.map((item) => (
            <label className="interest-choice" key={item.category}>
              <input
                aria-label={item.label}
                checked={selected.includes(item.category)}
                onChange={() => toggle(item.category)}
                type="checkbox"
              />
              <span>{item.label}</span>
              {item.status === 'EXPERIMENTAL' && <small>실험 중</small>}
            </label>
          ))}
        </fieldset>
      ) : (
        <section className="empty-panel">
          <h2>아직 공개 가능한 분야가 없습니다</h2>
          <p>충분한 실제 데이터와 검토 결과가 쌓이면 선택할 수 있어요.</p>
        </section>
      )}
      <p className="selection-hint">최소 1개 · 3~5개를 추천해요</p>
      {error && <p className="error" role="alert">{error}</p>}
      <button className="primary wide" disabled={!selected.length || saving} onClick={submit}>
        {saving ? '저장 중…' : '내 레이더 시작하기'}
      </button>
    </main>
  )
}
