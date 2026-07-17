import { useEffect } from "react"
import { Navigate, NavLink, Route, Routes } from "react-router-dom"
import { cn } from "@/lib/utils"
import AgentPage from "@/pages/AgentPage"
import CodePage from "@/pages/CodePage"
import CommsPage from "@/pages/CommsPage"

const tabs = [
  { to: "/agent", label: "Agent" },
  { to: "/code", label: "Code" },
  { to: "/comms", label: "Comms" },
]

function App() {
  useEffect(() => {
    fetch("http://localhost:8010/ping")
      .then((res) => res.json())
      .then((data) => console.log(data))
      .catch((err) => console.error(err))
  }, [])

  return (
    <div className="flex min-h-svh flex-col">
      <header className="flex items-center gap-6 border-b px-6 py-3">
        <span className="font-semibold">Sabio</span>
        <nav className="flex gap-4">
          {tabs.map((tab) => (
            <NavLink
              key={tab.to}
              to={tab.to}
              className={({ isActive }) =>
                cn(
                  "border-b-2 border-transparent pb-1 text-sm font-medium text-muted-foreground hover:text-foreground",
                  isActive && "border-foreground text-foreground",
                )
              }
            >
              {tab.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="flex-1">
        <Routes>
          <Route path="/" element={<Navigate to="/agent" replace />} />
          <Route path="/agent" element={<AgentPage />} />
          <Route path="/code" element={<CodePage />} />
          <Route path="/comms" element={<CommsPage />} />
        </Routes>
      </main>
    </div>
  )
}

export default App
