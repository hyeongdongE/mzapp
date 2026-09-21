import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, test, vi } from 'vitest'

import App from '../App'

const fetchMock = vi.fn()
vi.stubGlobal('fetch', fetchMock)

function jsonResponse(body: unknown, status = 200): Promise<Response> {
  return Promise.resolve(new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  }))
}

beforeEach(() => {
  fetchMock.mockReset()
  window.history.pushState({}, '', '/onboarding')
  fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input)
    if (path.endsWith('/session')) return jsonResponse({ isNew: true }, 201)
    if (path.endsWith('/categories')) return jsonResponse({
      dataMode: 'DEMO',
      items: [
        { category: 'AI_TECH', label: 'AI / IT', status: 'EXPERIMENTAL' },
        { category: 'FOOD', label: '음식', status: 'EXPERIMENTAL' },
        { category: 'GAME', label: '게임', status: 'EXPERIMENTAL' },
      ],
    })
    if (path.endsWith('/me/interests') && init?.method === 'PUT') {
      return jsonResponse({ categories: ['AI_TECH'] })
    }
    if (path.endsWith('/me/interests')) return jsonResponse({ categories: [] })
    if (path.endsWith('/events')) return jsonResponse({ accepted: true }, 202)
    throw new Error(`Unexpected request: ${path}`)
  })
})

test('labels demo data and requires at least one interest', async () => {
  render(<App />)
  const continueButton = await screen.findByRole('button', { name: '내 레이더 시작하기' })

  expect(screen.getByText(/DEMO DATA/)).toBeInTheDocument()
  expect(continueButton).toBeDisabled()

  await userEvent.click(screen.getByRole('checkbox', { name: 'AI / IT' }))
  expect(continueButton).toBeEnabled()
})

test('submits interests and navigates to the feed', async () => {
  render(<App />)

  await userEvent.click(await screen.findByRole('checkbox', { name: 'AI / IT' }))
  await userEvent.click(screen.getByRole('button', { name: '내 레이더 시작하기' }))

  await waitFor(() => expect(window.location.pathname).toBe('/feed'))
})
