import { useEffect, useState } from 'react'

import { api } from '../api'
import { useAppState } from '../App'
import type { Category } from '../types'

const notificationOptions = [
  ['OFF', '알림 끔'], ['DAILY_DIGEST', '하루 요약'], ['IMPORTANT_RISING', '중요한 상승만'],
] as const

export default function Settings() {
  const { catalog, setInterests } = useAppState()
  const [selected, setSelected] = useState<Category[]>([])
  const [notification, setNotification] = useState('OFF')
  const [phase, setPhase] = useState<'loading' | 'ready' | 'saving' | 'saved' | 'error'>('loading')
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    void api.settings().then((result) => {
      if (!active) return
      setSelected(result.categories)
      setNotification(result.notificationMode)
      setPhase('ready')
    }).catch(() => {
      if (!active) return
      setError('설정을 불러오지 못했어요.')
      setPhase('error')
    })
    return () => { active = false }
  }, [])

  function toggle(category: Category) {
    setSelected((current) => current.includes(category) ? current.filter((value) => value !== category) : [...current, category])
    setPhase('ready')
  }

  async function submit() {
    if (!selected.length || phase === 'saving') return
    setPhase('saving')
    setError('')
    try {
      await api.updateSettings(selected, notification)
      setInterests(selected)
      setPhase('saved')
    } catch {
      setError('설정을 저장하지 못했어요. 잠시 후 다시 시도해 주세요.')
      setPhase('ready')
    }
  }

  return (
    <main className="page settings-page">
      <header className="page-header compact-header"><p className="eyebrow">SOLOPILOT</p><h1>설정</h1><p className="lede">관심 분야와 알림 방식을 조정해요.</p></header>
      {phase === 'loading' && <section className="settings-group settings-loading" aria-live="polite"><div className="settings-skeleton" /><p>설정을 불러오는 중…</p></section>}
      {phase === 'error' && <section className="empty-panel"><h2>설정을 불러오지 못했어요</h2><button className="primary" onClick={() => window.location.reload()}>다시 시도</button></section>}
      {phase !== 'loading' && phase !== 'error' && <>
      <section className="settings-group"><div className="section-heading"><h2>관심 분야</h2><span>{selected.length}개 선택</span></div><div className="settings-options">{catalog.items.map((item) => (
        <label key={item.category}><input aria-label={item.label} checked={selected.includes(item.category)} disabled={phase === 'saving'} onChange={() => toggle(item.category)} type="checkbox" /><span>{item.label}</span></label>
      ))}</div></section>
      <section className="settings-group"><h2>알림</h2><p className="helper">원하는 방식을 미리 골라두세요. 실제 알림은 아직 보내지 않아요.</p><div className="radio-stack">{notificationOptions.map(([value, label]) => (
        <label key={value}><input checked={notification === value} disabled={phase === 'saving'} name="notification" onChange={() => { setNotification(value); setPhase('ready') }} type="radio" /><span>{label}</span></label>
      ))}</div></section>
      <section className="settings-group about-group"><h2>SoloPilot</h2><p>중요한 IT 변화를 확인 가능한 근거와 함께 5분 브리프로 정리해요.</p></section>
      {error && <p className="error" role="alert">{error}</p>}
      <button className="primary wide" disabled={!selected.length || phase === 'saving'} onClick={() => void submit()}>{phase === 'saving' ? '저장 중…' : phase === 'saved' ? '저장했습니다' : '설정 저장'}</button>
      </>}
    </main>
  )
}
