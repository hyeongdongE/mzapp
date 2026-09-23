import { ExternalLink } from 'lucide-react'

import type { DailyBriefItem } from '../types'

export default function BriefItem({ item, lead = false }: { item: DailyBriefItem; lead?: boolean }) {
  return (
    <article className={`brief-item${lead ? ' brief-item-lead' : ''}`}>
      <div className="brief-rank" aria-label={`${item.position}번째 항목`}>{String(item.position).padStart(2, '0')}</div>
      <p className="brief-category">{item.category.replaceAll('_', ' ')}</p>
      <h2>{item.headline}</h2>
      <section className="brief-copy">
        <h3>WHAT HAPPENED</h3>
        <p>{item.whatHappened}</p>
      </section>
      <section className="brief-copy">
        <h3>WHY IT MATTERS</h3>
        <p>{item.whyItMatters}</p>
      </section>
      <div className="brief-evidence-grid">
        <section className="brief-proof brief-proof-fact">
          <h3>FACT</h3>
          <ul>{item.fact.map((line) => <li key={line}>{line}</li>)}</ul>
        </section>
        <section className="brief-proof">
          <h3>INTERPRETATION</h3>
          <p>{item.interpretation.replace(/^해석:\s*/, '')}</p>
        </section>
        <section className="brief-proof">
          <h3>WATCH</h3>
          <p>{item.watch.replace(/^관찰:\s*/, '')}</p>
        </section>
      </div>
      <nav className="brief-sources" aria-label={`${item.headline} 출처`}>
        {item.sources.map((source) => (
          <a href={source.url} key={`${source.title}-${source.url}`} rel="noreferrer" target="_blank">
            {source.title} 원문 열기 <ExternalLink aria-hidden="true" size={15} />
          </a>
        ))}
      </nav>
    </article>
  )
}
