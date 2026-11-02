import { BrowserRouter, NavLink, Route, Routes } from 'react-router-dom'
import { business } from './data.ts'
import { isRisk } from './demo.ts'
import Main from './pages/Main.tsx'
import Simulation from './pages/Simulation.tsx'
import SimulationAsk from './pages/SimulationAsk.tsx'
import FinMap from './pages/FinMap.tsx'
import Agent from './pages/Agent.tsx'
import Ledger from './pages/Ledger.tsx'

export default function App() {
  return (
    <BrowserRouter>
      <div className="shell">
        <aside className="rail">
          <div>
            <div className="logo">상생여지도<small>소상공인 유동성 관리</small>{isRisk && <span className="demo-badge">위험 상황 데모</span>}</div>
            <nav className="nav" aria-label="주요 메뉴">
              <NavLink to="/" end className={({ isActive }) => (isActive ? 'on' : '')}>홈</NavLink>
              <NavLink to="/map" className={({ isActive }) => (isActive ? 'on' : '')}>원인 보기</NavLink>
              <NavLink to="/simulation" className={({ isActive }) => (isActive ? 'on' : '')}>시나리오</NavLink>
              <NavLink to="/agent" className={({ isActive }) => (isActive ? 'on' : '')}>대응안</NavLink>
              <NavLink to="/ledger" className={({ isActive }) => (isActive ? 'on' : '')}>내 거래·일정</NavLink>
            </nav>
          </div>
          <div className="profile">
            <div className="avatar" aria-hidden>한</div>
            <div><b>{business.name}</b><span>{business.region}</span></div>
          </div>
        </aside>
        <div className="content">
          <Routes>
            <Route path="/" element={<Main />} />
            <Route path="/simulation" element={<Simulation />} />
            <Route path="/simulation/ask" element={<SimulationAsk />} />
            <Route path="/map" element={<FinMap />} />
            <Route path="/agent" element={<Agent />} />
            <Route path="/ledger" element={<Ledger />} />
          </Routes>
        </div>
      </div>
    </BrowserRouter>
  )
}
