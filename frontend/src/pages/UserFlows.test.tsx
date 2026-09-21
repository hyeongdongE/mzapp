import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, test, vi } from 'vitest'

import App from '../App'
import SourceList from '../components/SourceList'

const fetchMock = vi.fn()
vi.stubGlobal('fetch', fetchMock)

const card = {
  trendId: 'trend-1',
  title: '피스타치오 디저트',
  category: 'FOOD',
  lifecycle: 'RISING',
  summary: '최근 관심 증가가 관측되었습니다.',
  firstSeenAt: '2026-09-21T01:00:00+00:00',
  observedAt: '2026-09-21T04:00:00+00:00',
  sourceNames: ['WIKIMEDIA'],
  saved: false,
  feedback: null,
  rankingReasons: ['선택한 관심 분야'],
  dataMode: 'DEMO',
}

function response(body: unknown, status = 200): Promise<Response> {
  return Promise.resolve(new Response(JSON.stringify(body), {
    status, headers: { 'Content-Type': 'application/json' },
  }))
}

function installApi(
  items = [card],
  settingsRequests: { get?: Promise<Response>; put?: Promise<Response> } = {},
) {
  fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input)
    if (path.endsWith('/session')) return response({ isNew: false }, 201)
    if (path.endsWith('/categories')) return response({ dataMode: 'DEMO', items: [
      { category: 'FOOD', label: '음식', status: 'EXPERIMENTAL' },
      { category: 'AI_TECH', label: 'AI / IT', status: 'EXPERIMENTAL' },
    ] })
    if (path.endsWith('/me/interests')) return response({ categories: ['FOOD'] })
    if (path.endsWith('/feed')) return response({ dataMode: 'DEMO', items })
    if (path.endsWith('/saved')) return response({ dataMode: 'DEMO', items })
    if (path.endsWith('/settings') && init?.method === 'PUT') return settingsRequests.put ?? response({})
    if (path.endsWith('/settings')) return settingsRequests.get ?? response({ categories: ['FOOD'], notificationMode: 'OFF', pushDeliveryEnabled: false })
    if (path.endsWith('/trends/trend-1') && !init?.method) return response({
      ...card,
      what: '피스타치오를 활용한 디저트입니다.',
      why: '관심 증가는 확인되었지만 증가 원인은 확인되지 않았습니다.',
      sources: [{ source: 'WIKIMEDIA', url: 'https://wikimedia.org/example', observedAt: card.observedAt }],
    })
    if (path.endsWith('/feedback')) return response({ feedback: 'NEW_AND_USEFUL' })
    if (path.endsWith('/save')) return init?.method === 'DELETE' ? Promise.resolve(new Response(null, { status: 204 })) : response({ saved: true })
    if (path.endsWith('/events')) return response({ accepted: true }, 202)
    throw new Error(`Unexpected request: ${path}`)
  })
}

beforeEach(() => {
  fetchMock.mockReset()
})

test('mobile app shell exposes four primary destinations including Explore', async () => {
  installApi()
  window.history.pushState({}, '', '/feed')
  render(<App />)

  const navigation = await screen.findByRole('navigation', { name: '주요 메뉴' })
  expect(navigation).toHaveClass('bottom-nav')
  expect(screen.getByRole('link', { name: '홈' })).toHaveAttribute('href', '/feed')
  expect(screen.getByRole('link', { name: '둘러보기' })).toHaveAttribute('href', '/explore')
  expect(screen.getByRole('link', { name: '저장' })).toHaveAttribute('href', '/saved')
  expect(screen.getByRole('link', { name: '설정' })).toHaveAttribute('href', '/settings')
})

test('feed shows lifecycle hierarchy and records useful feedback', async () => {
  installApi()
  window.history.pushState({}, '', '/feed')
  render(<App />)

  expect(await screen.findByText('피스타치오 디저트')).toBeInTheDocument()
  expect(screen.getByText('관심 상승 중')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '전체' })).toHaveAttribute('aria-pressed', 'true')
  await userEvent.click(screen.getByRole('button', { name: '처음 봤어요 ✨' }))

  await waitFor(() => expect(screen.getByRole('button', { name: '처음 봤어요 ✨' })).toHaveAttribute('aria-pressed', 'true'))
})

test('saving a feed card confirms the action without leaving the feed', async () => {
  installApi()
  window.history.pushState({}, '', '/feed')
  render(<App />)

  await screen.findByText('피스타치오 디저트')
  await userEvent.click(screen.getByRole('button', { name: '저장' }))

  expect(await screen.findByRole('status')).toHaveTextContent('저장했어요')
  expect(screen.getByRole('button', { name: '저장 취소' })).toHaveAttribute('aria-pressed', 'true')
})

test('Explore reuses eligible feed cards without presenting a fake search', async () => {
  installApi()
  window.history.pushState({}, '', '/explore')
  render(<App />)

  expect(await screen.findByRole('heading', { name: '요즘 뜨는 분야' })).toBeInTheDocument()
  expect(await screen.findByText('피스타치오 디저트')).toBeInTheDocument()
  expect(screen.queryByRole('searchbox')).not.toBeInTheDocument()
})

test('feed preserves an honest empty state', async () => {
  installApi([])
  window.history.pushState({}, '', '/feed')
  render(<App />)

  expect(await screen.findByText('아직 새로운 흐름이 없어요')).toBeInTheDocument()
})

test('route transitions reset the document scroll position', async () => {
  installApi()
  window.history.pushState({}, '', '/feed')
  render(<App />)

  const trend = await screen.findByRole('link', { name: /피스타치오 디저트/ })
  document.documentElement.scrollTop = 420
  await userEvent.click(trend)

  await waitFor(() => expect(window.location.pathname).toBe('/trends/trend-1'))
  expect(document.documentElement.scrollTop).toBe(0)
})

test('detail presents supported explanation, unknown cause, and attribution', async () => {
  installApi()
  window.history.pushState({}, '', '/trends/trend-1')
  render(<App />)

  expect(await screen.findByText('피스타치오를 활용한 디저트입니다.')).toBeInTheDocument()
  expect(screen.getByText(/증가 원인은 확인되지 않았습니다/)).toBeInTheDocument()
  expect(screen.getByRole('link', { name: /Wikimedia에서 확인/ })).toHaveAttribute('href', 'https://wikimedia.org/example')
  const save = screen.getByRole('button', { name: '저장' })
  await userEvent.click(save)
  await waitFor(() => expect(screen.getByRole('button', { name: '저장 취소' })).toHaveAttribute('aria-pressed', 'true'))
  expect(screen.getByRole('button', { name: '내용이 부정확해요' })).toBeInTheDocument()
})

test('saved and settings routes render persisted user state', async () => {
  installApi()
  window.history.pushState({}, '', '/saved')
  const { unmount } = render(<App />)
  expect(await screen.findByText('피스타치오 디저트')).toBeInTheDocument()
  unmount()

  window.history.pushState({}, '', '/settings')
  render(<App />)
  const food = await screen.findByRole('checkbox', { name: '음식' })
  await waitFor(() => expect(food).toBeChecked())
  expect(screen.getByRole('radio', { name: '알림 끔' })).toBeChecked()
  expect(screen.getByText(/실제 알림은 아직 보내지 않아요/)).toBeInTheDocument()
})

test('Saved removes an unsaved card and Detail returns to the originating screen', async () => {
  installApi([{ ...card, saved: true }])
  window.history.pushState({}, '', '/saved')
  render(<App />)

  const trend = await screen.findByRole('link', { name: /피스타치오 디저트/ })
  await userEvent.click(trend)
  await waitFor(() => expect(window.location.pathname).toBe('/trends/trend-1'))
  await userEvent.click(await screen.findByRole('link', { name: '이전 화면으로 돌아가기' }))
  await waitFor(() => expect(window.location.pathname).toBe('/saved'))

  await userEvent.click(await screen.findByRole('button', { name: '저장 취소' }))
  expect(await screen.findByText('아직 저장한 트렌드가 없어요')).toBeInTheDocument()
  expect(screen.queryByText('피스타치오 디저트')).not.toBeInTheDocument()
})

test('settings waits for persisted values and locks the form while saving', async () => {
  let resolveGet!: (value: Response) => void
  let resolvePut!: (value: Response) => void
  const get = new Promise<Response>((resolve) => { resolveGet = resolve })
  const put = new Promise<Response>((resolve) => { resolvePut = resolve })
  installApi([card], { get, put })
  window.history.pushState({}, '', '/settings')
  render(<App />)

  expect(await screen.findByText('설정을 불러오는 중…')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '설정 저장' })).not.toBeInTheDocument()

  resolveGet(await response({ categories: ['FOOD'], notificationMode: 'OFF', pushDeliveryEnabled: false }))
  const save = await screen.findByRole('button', { name: '설정 저장' })
  await userEvent.click(save)
  expect(screen.getByRole('button', { name: '저장 중…' })).toBeDisabled()

  resolvePut(await response({}))
  expect(await screen.findByRole('button', { name: '저장했습니다' })).toBeEnabled()
})

test('source labels never expose internal source enums', () => {
  render(<SourceList sources={[
    { source: 'DEMO_FIXTURE', url: 'https://example.test/demo', observedAt: card.observedAt },
    { source: 'FUTURE_SOURCE_ENUM', url: 'https://example.test/future', observedAt: card.observedAt },
  ]} />)

  expect(screen.getByRole('link', { name: /데모 데이터에서 확인/ })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: /공식 데이터 소스에서 확인/ })).toBeInTheDocument()
  expect(screen.queryByText(/DEMO_FIXTURE|FUTURE_SOURCE_ENUM/)).not.toBeInTheDocument()
})
