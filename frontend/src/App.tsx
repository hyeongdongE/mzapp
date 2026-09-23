import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { Bookmark, Newspaper, Radar, Settings as SettingsIcon } from 'lucide-react'

import { api } from './api'
import Onboarding from './pages/Onboarding'
import Feed from './pages/Feed'
import Explore from './pages/Explore'
import Saved from './pages/Saved'
import Settings from './pages/Settings'
import TrendDetail from './pages/TrendDetail'
import Today from './pages/Today'
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

function RootRedirect() {
  return <Navigate replace to="/today" />
}

function BottomNav() {
  const location = useLocation()
  if (location.pathname === '/onboarding') return null
  const items = [
    { to: '/today', label: 'Today', icon: Newspaper },
    { to: '/radar', label: 'Radar', icon: Radar },
    { to: '/saved', label: '저장', icon: Bookmark },
    { to: '/settings', label: '설정', icon: SettingsIcon },
  ]
  return (
    <nav className="bottom-nav" aria-label="주요 메뉴">
      {items.map(({ to, label, icon: Icon }) => (
        <Link aria-current={location.pathname.startsWith(to) ? 'page' : undefined} className={location.pathname.startsWith(to) ? 'active' : ''} key={to} to={to}>
          <Icon aria-hidden="true" size={20} strokeWidth={2.1} />
          <span>{label}</span>
        </Link>
      ))}
    </nav>
  )
}

function RouteReset() {
  const { pathname } = useLocation()
  useEffect(() => {
    document.documentElement.scrollTop = 0
    document.body.scrollTop = 0
  }, [pathname])
  return null
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
  if (loading) return <main className="state-page" aria-live="polite"><span className="radar-dot" />SoloPilot을 준비하고 있어요.</main>
  if (error) return <main className="state-page"><h1>잠시 연결이 어렵습니다</h1><p>{error}</p><button onClick={() => window.location.reload()}>다시 시도</button></main>

  return (
    <AppContext.Provider value={state}>
      <RouteReset />
      {catalog.dataMode === 'DEMO' && <div className="demo-banner">DEMO DATA · 실제 트렌드가 아닙니다</div>}
      <Routes>
        <Route path="/" element={<RootRedirect />} />
        <Route path="/onboarding" element={<Onboarding />} />
        <Route path="/today" element={<Today />} />
        <Route path="/radar" element={<Explore />} />
        <Route path="/feed" element={<Feed />} />
        <Route path="/explore" element={<Navigate replace to="/radar" />} />
        <Route path="/trends/:id" element={<TrendDetail />} />
        <Route path="/saved" element={<Saved />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<Navigate replace to="/" />} />
      </Routes>
      <BottomNav />
    </AppContext.Provider>
  )
}

export default function App() {
  return <BrowserRouter><Shell /></BrowserRouter>
}
