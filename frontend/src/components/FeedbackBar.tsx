import { useState } from 'react'

import { api } from '../api'
import type { Feedback } from '../types'

const options: Array<{ value: Feedback; label: string }> = [
  { value: 'NEW_AND_USEFUL', label: '처음 알았음' },
  { value: 'ALREADY_KNEW', label: '이미 알았음' },
  { value: 'NOT_INTERESTED', label: '관심 없음' },
]

export default function FeedbackBar({ trendId, initial }: { trendId: string; initial: Feedback | null }) {
  const [selected, setSelected] = useState(initial)
  const [busy, setBusy] = useState(false)

  async function choose(value: Feedback) {
    setBusy(true)
    try {
      const result = await api.feedback(trendId, value)
      setSelected(result.feedback)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="feedback-bar" aria-label="이 트렌드에 대한 의견">
      {options.map((option) => (
        <button
          aria-pressed={selected === option.value}
          disabled={busy}
          key={option.value}
          onClick={() => void choose(option.value)}
          type="button"
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}
