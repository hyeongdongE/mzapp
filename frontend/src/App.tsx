import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation } from 'react-router-dom'

import { api } from './api'
import Onboarding from './pages/Onboarding'
import type { CategoriesResponse, Category } from './types'

interface AppContextValue {
  catalog: CategoriesResponse
  interests: Category[]
  setInterests: (categories: Category[]) => void
}

const AppContext = createContext<AppContextValue | null>(null)

export function useAppState(): AppContextValue {
  const state = useContext(AppContext)
  if (!state) throw new Error('App state is unavailable')
  return state
}

function Placeholder({ title }: { title: string }) {
  return <main className="page"><h1>{title}</h1><p>화면을 준비하고 있습니다.</p></main>
}

function RootRedirect() {
  const { interests } = useAppState()
  return <Navigate replace to={interests.length ? '/feed' : '/onboarding'} />
}

function BottomNav() {
  const location = useLocation()
  if (location.pathname === '/onboarding') return null
  return (
    <nav className="bottom-nav" aria-label="주요 메뉴">
      <Link className={location.pathname.startsWith('/feed') ? 'active' : ''} to="/feed">피드</Link>
      <Link className={location.pathname.startsWith('/saved') ? 'active' : ''} to="/saved">저장</Link>
      <Link className={location.pathname.startsWith('/settings') ? 'active' : ''} to="/settings">설정</Link>
    </nav>
  )
}

function Shell() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [catalog, setCatalog] = useState<CategoriesResponse>({ dataMode: 'LIVE', items: [] })
  const [interests, setInterests] = useState<Category[]>([])

  useEffect(() => {
    let active = true
    Promise.all([api.createSession(), api.categories()])
      .then(async ([, categories]) => {
        const selected = await api.interests()
        if (!active) return
        setCatalog(categories)
        setInterests(selected.categories)
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : '연결할 수 없습니다.')
      })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  const state = useMemo(() => ({ catalog, interests, setInterests }), [catalog, interests])
  if (loading) return <main className="state-page" aria-live="polite"><span className="radar-dot" />레이더를 준비하고 있어요.</main>
  if (error) return <main className="state-page"><h1>잠시 연결이 어렵습니다</h1><p>{error}</p><button onClick={() => window.location.reload()}>다시 시도</button></main>

  return (
    <AppContext.Provider value={state}>
      {catalog.dataMode === 'DEMO' && <div className="demo-banner">DEMO DATA · 실제 트렌드가 아닙니다</div>}
      <Routes>
        <Route path="/" element={<RootRedirect />} />
        <Route path="/onboarding" element={<Onboarding />} />
        <Route path="/feed" element={<Placeholder title="나의 트렌드" />} />
        <Route path="/trends/:id" element={<Placeholder title="트렌드 상세" />} />
        <Route path="/saved" element={<Placeholder title="저장한 트렌드" />} />
        <Route path="/settings" element={<Placeholder title="설정" />} />
        <Route path="*" element={<Navigate replace to="/" />} />
      </Routes>
      <BottomNav />
    </AppContext.Provider>
  )
}

export default function App() {
  return <BrowserRouter><Shell /></BrowserRouter>
}
