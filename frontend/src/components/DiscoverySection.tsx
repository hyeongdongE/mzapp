import type { DiscoveryFeed } from '../types'

export default function DiscoverySection({ feed }: { feed: DiscoveryFeed | null }) {
  if (!feed || feed.items.length === 0) return null

  return (
    <section className="discovery-section" aria-label="확인 전 소식">
      <p className="eyebrow">GEEKNEWS · 확인 전 소식</p>
      <h2>새로 올라온 글</h2>
      <p>제목과 링크만 표시합니다. 내용의 사실 여부와 중요도는 아직 검증하지 않았으며, 검증된 브리프와 별개입니다.</p>
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
