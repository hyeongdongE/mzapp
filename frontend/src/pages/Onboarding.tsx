import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Check, Clapperboard, Gamepad2, Shirt, ShoppingBag, Sparkles, Trophy, Utensils } from 'lucide-react'

import { api } from '../api'
import { useAppState } from '../App'
import BrandMark from '../components/BrandMark'
import type { Category } from '../types'

const categoryIcons = {
  SPORTS: Trophy,
  ENTERTAINMENT: Clapperboard,
  FOOD: Utensils,
  GAME: Gamepad2,
  AI_TECH: Sparkles,
  MEME_INTERNET: Sparkles,
  FASHION_BEAUTY: Shirt,
  SHOPPING_PRODUCT: ShoppingBag,
} satisfies Record<Category, typeof Sparkles>

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
      <div className="brand-lockup"><BrandMark size={38} /><span>MZ RADAR</span></div>
      <header className="onboarding-header">
        <h1>요즘 뜨는 것만,<br /><span>네 취향대로.</span></h1>
        <p className="lede">관심 있는 분야를 고르면<br />새로운 흐름만 골라드릴게요.</p>
      </header>
      {catalog.items.length ? (
        <fieldset className="interest-grid">
          <legend className="sr-only">관심 분야</legend>
          {catalog.items.map((item) => {
            const Icon = categoryIcons[item.category]
            const checked = selected.includes(item.category)
            return (
            <label className="interest-choice" data-category={item.category} key={item.category}>
              <input
                aria-label={item.label}
                checked={checked}
                onChange={() => toggle(item.category)}
                type="checkbox"
              />
              <span className="interest-icon"><Icon aria-hidden="true" size={22} /></span>
              <span className="interest-label">{item.label}</span>
              <Check aria-hidden="true" className="interest-check" size={18} />
            </label>
          )})}
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
        {saving ? '저장 중…' : '계속하기'}
      </button>
    </main>
  )
}
