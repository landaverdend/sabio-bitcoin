import { useEffect } from "react"
import { Navigate, Route, Routes } from "react-router-dom"
import { AppSidebar } from "@/components/app-sidebar"
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar"
import { TooltipProvider } from "@/components/ui/tooltip"
import ChatPage from "@/pages/ChatPage"
import CodePage from "@/pages/CodePage"
import CommsPage from "@/pages/CommsPage"
import PeoplePage from "@/pages/PeoplePage"
import CommitDetailPage from "@/pages/code/CommitDetailPage"
import CommitsPage from "@/pages/code/CommitsPage"
import PersonDetailPage from "@/pages/people/PersonDetailPage"

function App() {
  useEffect(() => {
    fetch("/ping")
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
          <main className="min-h-0 min-w-0 flex-1">
            <Routes>
              <Route path="/" element={<Navigate to="/chat" replace />} />
              <Route path="/chat" element={<ChatPage />} />
              <Route path="/code" element={<CodePage />} />
              {/* Wildcard, not :ref -- refs for non-default branches only
                  resolve as "origin/<name>", which contains a "/" and
                  wouldn't match a single dynamic segment. */}
              <Route path="/code/tree/*" element={<CodePage />} />
              <Route path="/code/commits" element={<CommitsPage />} />
              <Route path="/code/commits/*" element={<CommitsPage />} />
              <Route path="/code/commit/:sha" element={<CommitDetailPage />} />
              <Route path="/comms" element={<CommsPage />} />
              <Route path="/people" element={<PeoplePage />} />
              <Route path="/people/:id" element={<PersonDetailPage />} />
            </Routes>
          </main>
        </SidebarInset>
      </SidebarProvider>
    </TooltipProvider>
  )
}

export default App
