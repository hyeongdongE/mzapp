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
      <p className="eyebrow">PREFERENCES</p><h1>내 레이더<br />설정</h1>
      <section><h2>관심 분야</h2><div className="settings-options">{catalog.items.map((item) => (
        <label key={item.category}><input aria-label={item.label} checked={selected.includes(item.category)} onChange={() => toggle(item.category)} type="checkbox" /><span>{item.label}</span></label>
      ))}</div></section>
      <section><h2>알림</h2><p className="helper">이번 MVP에서는 선호만 저장하며 실제 Push는 보내지 않습니다.</p><div className="radio-stack">{notificationOptions.map(([value, label]) => (
        <label key={value}><input checked={notification === value} name="notification" onChange={() => setNotification(value)} type="radio" /><span>{label}</span></label>
      ))}</div></section>
      <button className="primary wide" disabled={!selected.length} onClick={() => void submit()}>{saved ? '저장했습니다' : '설정 저장'}</button>
    </main>
  )
}
