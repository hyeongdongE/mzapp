import type { CategoriesResponse, Category, Feedback, TodayBrief, TrendDetail, TrendItem } from './types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: 'same-origin',
    headers: init?.body ? { 'Content-Type': 'application/json', ...init.headers } : init?.headers,
    ...init,
  })
  if (!response.ok) throw new Error(`요청을 완료하지 못했습니다 (${response.status})`)
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export const api = {
  createSession: () => request<{ isNew: boolean }>('/api/public/session', { method: 'POST' }),
  categories: () => request<CategoriesResponse>('/api/public/categories'),
  interests: () => request<{ categories: Category[] }>('/api/public/me/interests'),
  updateInterests: (categories: Category[]) => request<{ categories: Category[] }>('/api/public/me/interests', {
    method: 'PUT',
    body: JSON.stringify({ categories }),
  }),
  feed: () => request<{ dataMode: 'LIVE' | 'DEMO'; items: TrendItem[] }>('/api/public/feed'),
  today: () => request<TodayBrief>('/api/public/today'),
  trend: (id: string) => request<TrendDetail>(`/api/public/trends/${id}`),
  feedback: (id: string, feedbackType: Feedback) => request<{ feedback: Feedback }>(`/api/public/trends/${id}/feedback`, {
    method: 'PUT', body: JSON.stringify({ feedbackType }),
  }),
  save: (id: string) => request<{ saved: true }>(`/api/public/trends/${id}/save`, { method: 'PUT' }),
  unsave: (id: string) => request<void>(`/api/public/trends/${id}/save`, { method: 'DELETE' }),
  saved: () => request<{ dataMode: 'LIVE' | 'DEMO'; items: TrendItem[] }>('/api/public/saved'),
  settings: () => request<{ categories: Category[]; notificationMode: string; pushDeliveryEnabled: false }>('/api/public/settings'),
  updateSettings: (categories: Category[], notificationMode: string) => request('/api/public/settings', {
    method: 'PUT', body: JSON.stringify({ categories, notificationMode }),
  }),
  event: (eventType: string, trendId?: string) => request('/api/public/events', {
    method: 'POST', body: JSON.stringify({ eventType, trendId }),
  }),
}
