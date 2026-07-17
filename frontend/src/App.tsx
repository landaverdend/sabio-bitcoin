import { useEffect } from "react"
import { Navigate, Route, Routes } from "react-router-dom"
import { AppSidebar } from "@/components/app-sidebar"
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar"
import { TooltipProvider } from "@/components/ui/tooltip"
import AgentPage from "@/pages/AgentPage"
import CodePage from "@/pages/CodePage"
import CommsPage from "@/pages/CommsPage"

function App() {
  useEffect(() => {
    fetch("http://localhost:8010/ping")
      .then((res) => res.json())
      .then((data) => console.log(data))
      .catch((err) => console.error(err))
  }, [])

  return (
    <TooltipProvider>
      <SidebarProvider>
        <AppSidebar />
        <SidebarInset>
          <header className="flex h-14 shrink-0 items-center gap-2 border-b px-4">
            <SidebarTrigger />
          </header>
          <main className="flex-1">
            <Routes>
              <Route path="/" element={<Navigate to="/agent" replace />} />
              <Route path="/agent" element={<AgentPage />} />
              <Route path="/code" element={<CodePage />} />
              <Route path="/comms" element={<CommsPage />} />
            </Routes>
          </main>
        </SidebarInset>
      </SidebarProvider>
    </TooltipProvider>
  )
}

export default App
