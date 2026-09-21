import { Clock, ExternalLink } from 'lucide-react'

const sourceLabels: Record<string, string> = {
  GOOGLE_TRENDS: 'Google Trends',
  WIKIMEDIA: 'Wikimedia',
}

function observedLabel(value: string) {
  const date = new Date(value)
  const now = new Date()
  const time = date.toLocaleTimeString('ko-KR', { hour: 'numeric', minute: '2-digit' })
  return date.toDateString() === now.toDateString()
    ? `오늘 ${time} 기준`
    : `${date.toLocaleDateString('ko-KR', { month: 'long', day: 'numeric' })} ${time} 기준`
}

export default function SourceList({ sources }: { sources: Array<{ source: string; url: string; observedAt: string }> }) {
  return (
    <ul className="source-list">
      {sources.map((source) => (
        <li key={`${source.source}-${source.url}`}>
          <a href={source.url} rel="noreferrer" target="_blank">{sourceLabels[source.source] ?? source.source}에서 확인 <ExternalLink aria-hidden="true" size={15} /></a>
          <time dateTime={source.observedAt}><Clock aria-hidden="true" size={14} />{observedLabel(source.observedAt)}</time>
        </li>
      ))}
    </ul>
  )
}
