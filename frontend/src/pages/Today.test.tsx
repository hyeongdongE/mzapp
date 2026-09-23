import { render, screen } from '@testing-library/react'
import { beforeEach, expect, test, vi } from 'vitest'

import App from '../App'

const fetchMock = vi.fn()
vi.stubGlobal('fetch', fetchMock)

const brief = {
  briefDate: '2026-09-24',
  status: 'PUBLISHED',
  todayInOneLine: '보안과 개발 도구에서 중요한 변화가 있었습니다.',
  readingTimeSeconds: 248,
  emptyStateMessage: null,
  statistics: {
    rawItemCount: 42,
    eventClusterCount: 9,
    candidateCount: 6,
    selectedCount: 3,
  },
  items: [{
    position: 1,
    headline: 'Claude Code v2.1.0 released',
    category: 'DEVELOPER_TOOLS',
    whatHappened: '새 버전이 공개됐습니다.',
    whyItMatters: '개발 워크플로에 영향을 줄 수 있습니다.',
    fact: ['버전: v2.1.0', '발행일: 2026-09-23'],
    interpretation: '해석: 적용 범위를 확인해야 합니다.',
    watch: '관찰: 공식 후속 공지를 확인하세요.',
    sources: [
      { title: 'GitHub', url: 'https://github.com/anthropics/claude-code/releases/2.1.0' },
      { title: 'AWS', url: 'https://aws.amazon.com/blogs/aws/claude-code' },
    ],
    importance: 90,
  }],
}

function response(body: unknown, status = 200): Promise<Response> {
  return Promise.resolve(new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  }))
}

function installApi(todayResponse: Promise<Response> = response(brief)) {
  fetchMock.mockImplementation((input: RequestInfo | URL) => {
    const path = String(input)
    if (path.endsWith('/session')) return response({ isNew: false }, 201)
    if (path.endsWith('/categories')) return response({ dataMode: 'LIVE', items: [] })
    if (path.endsWith('/me/interests')) return response({ categories: ['AI_TECH'] })
    if (path.endsWith('/today')) return todayResponse
    throw new Error(`Unexpected request: ${path}`)
  })
}

beforeEach(() => {
  fetchMock.mockReset()
  window.history.pushState({}, '', '/today')
})

test('renders an evidence-grounded brief without save controls', async () => {
  installApi()
  render(<App />)

  expect(await screen.findByRole('heading', { name: '오늘의 IT 5분' })).toBeInTheDocument()
  expect(screen.getByText('FACT')).toBeInTheDocument()
  expect(screen.getByText('INTERPRETATION')).toBeInTheDocument()
  expect(screen.getByText('WATCH')).toBeInTheDocument()
  expect(screen.getByText('약 5분 이내 · 4분 8초')).toBeInTheDocument()
  expect(screen.getByText('원문 42개 → 사건 9개 → 오늘 3개')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'GitHub 원문 열기' })).toHaveAttribute(
    'href',
    'https://github.com/anthropics/claude-code/releases/2.1.0',
  )
  expect(screen.queryByRole('button', { name: /저장/ })).not.toBeInTheDocument()
})

test('renders a healthy low-signal day honestly', async () => {
  installApi(response({
    ...brief,
    status: 'LOW_SIGNAL_DAY',
    emptyStateMessage: '오늘은 기준을 충족한 중요한 변화가 없습니다.',
    items: [],
    statistics: { ...brief.statistics, selectedCount: 0 },
  }))
  render(<App />)

  expect(await screen.findByText('오늘은 기준을 충족한 중요한 변화가 없습니다.')).toBeInTheDocument()
})

test('renders an unavailable state when no public brief exists', async () => {
  installApi(response({ detail: 'published brief not found' }, 404))
  render(<App />)

  expect(await screen.findByText('오늘 브리프를 아직 공개하지 못했습니다')).toBeInTheDocument()
})
