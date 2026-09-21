export default function SourceList({ sources }: { sources: Array<{ source: string; url: string; observedAt: string }> }) {
  return (
    <ul className="source-list">
      {sources.map((source) => (
        <li key={`${source.source}-${source.url}`}>
          <a href={source.url} rel="noreferrer" target="_blank">{source.source} 원문</a>
          <time dateTime={source.observedAt}>{new Date(source.observedAt).toLocaleString('ko-KR')}</time>
        </li>
      ))}
    </ul>
  )
}
