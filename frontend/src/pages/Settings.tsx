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
  const [saved, setSaved] = useState(false)
  useEffect(() => { void api.settings().then((result) => {
    setSelected(result.categories); setNotification(result.notificationMode)
  }) }, [])

  function toggle(category: Category) {
    setSelected((current) => current.includes(category) ? current.filter((value) => value !== category) : [...current, category])
  }

  async function submit() {
    if (!selected.length) return
    await api.updateSettings(selected, notification)
    setInterests(selected); setSaved(true)
  }

  return (
    <main className="page settings-page">
      <header className="page-header compact-header"><p className="eyebrow">MY RADAR</p><h1>설정</h1><p className="lede">내 취향에 맞게 레이더를 조정해요.</p></header>
      <section className="settings-group"><div className="section-heading"><h2>관심 분야</h2><span>{selected.length}개 선택</span></div><div className="settings-options">{catalog.items.map((item) => (
        <label key={item.category}><input aria-label={item.label} checked={selected.includes(item.category)} onChange={() => toggle(item.category)} type="checkbox" /><span>{item.label}</span></label>
      ))}</div></section>
      <section className="settings-group"><h2>알림</h2><p className="helper">원하는 방식을 미리 골라두세요. 실제 알림은 아직 보내지 않아요.</p><div className="radio-stack">{notificationOptions.map(([value, label]) => (
        <label key={value}><input checked={notification === value} name="notification" onChange={() => setNotification(value)} type="radio" /><span>{label}</span></label>
      ))}</div></section>
      <section className="settings-group about-group"><h2>Trend Radar</h2><p>미래를 예측하지 않아요. 최근 새롭게 관심이 늘고 있는 흐름만 확인 가능한 근거와 함께 보여드려요.</p></section>
      <button className="primary wide" disabled={!selected.length} onClick={() => void submit()}>{saved ? '저장했습니다' : '설정 저장'}</button>
    </main>
  )
}
