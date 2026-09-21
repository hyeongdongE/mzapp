import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, test, vi } from 'vitest'

import App from '../App'

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

function installApi(items = [card]) {
  fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input)
    if (path.endsWith('/session')) return response({ anonymousId: 'u1', isNew: false }, 201)
    if (path.endsWith('/categories')) return response({ dataMode: 'DEMO', items: [
      { category: 'FOOD', label: '음식', status: 'EXPERIMENTAL' },
      { category: 'AI_TECH', label: 'AI / IT', status: 'EXPERIMENTAL' },
    ] })
    if (path.endsWith('/me/interests')) return response({ categories: ['FOOD'] })
    if (path.endsWith('/feed')) return response({ dataMode: 'DEMO', items })
    if (path.endsWith('/saved')) return response({ dataMode: 'DEMO', items })
    if (path.endsWith('/settings') && init?.method === 'PUT') return response({})
    if (path.endsWith('/settings')) return response({ categories: ['FOOD'], notificationMode: 'OFF', pushDeliveryEnabled: false })
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

test('feed shows lifecycle hierarchy and records useful feedback', async () => {
  installApi()
  window.history.pushState({}, '', '/feed')
  render(<App />)

  expect(await screen.findByText('피스타치오 디저트')).toBeInTheDocument()
  expect(screen.getByText('관심 상승 중')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: '처음 알았음' }))

  await waitFor(() => expect(screen.getByRole('button', { name: '처음 알았음' })).toHaveAttribute('aria-pressed', 'true'))
})

test('feed preserves an honest empty state', async () => {
  installApi([])
  window.history.pushState({}, '', '/feed')
  render(<App />)

  expect(await screen.findByText('오늘은 아직 새로운 변화가 없습니다.')).toBeInTheDocument()
})

test('detail presents supported explanation, unknown cause, and attribution', async () => {
  installApi()
  window.history.pushState({}, '', '/trends/trend-1')
  render(<App />)

  expect(await screen.findByText('피스타치오를 활용한 디저트입니다.')).toBeInTheDocument()
  expect(screen.getByText(/증가 원인은 확인되지 않았습니다/)).toBeInTheDocument()
  expect(screen.getByRole('link', { name: /WIKIMEDIA/ })).toHaveAttribute('href', 'https://wikimedia.org/example')
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
})
