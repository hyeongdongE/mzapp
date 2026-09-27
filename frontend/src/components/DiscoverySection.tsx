import type { DiscoveryFeed } from '../types'

export default function DiscoverySection({ feed }: { feed: DiscoveryFeed | null }) {
  if (!feed || feed.items.length === 0) return null

  return (
    <section className="discovery-section" aria-label="긱뉴스 새 글">
      <p className="eyebrow">GEEKNEWS</p>
      <h2>새로 올라온 글</h2>
      <ul>
        {feed.items.map((item) => (
          <li key={item.url}>
            <a href={item.url} target="_blank" rel="noreferrer">{item.title}</a>
            <time dateTime={item.publishedAt}>{new Date(item.publishedAt).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Seoul' })}</time>
          </li>
        ))}
      </ul>
    </section>
  )
}
