import { useEffect } from "react"
import { Navigate, Route, Routes } from "react-router-dom"
import { AppHeader } from "@/components/app-header"
import { AppSidebar } from "@/components/app-sidebar"
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar"
import { TooltipProvider } from "@/components/ui/tooltip"
import { AuthProvider } from "@/lib/auth"
import { DEFAULT_REPO } from "@/lib/repos"
import AboutPage from "@/pages/AboutPage"
import ChatPage from "@/pages/ChatPage"
import CodePage from "@/pages/CodePage"
import PeoplePage from "@/pages/PeoplePage"
import CommitDetailPage from "@/pages/code/CommitDetailPage"
import CommitsPage from "@/pages/code/CommitsPage"
import { ChatProvider } from "@/pages/chat/chat-provider"
import PersonDetailPage from "@/pages/people/PersonDetailPage"

function App() {
  useEffect(() => {
    fetch("/ping")
      .then((res) => res.json())
      .then((data) => console.log(data))
      .catch((err) => console.error(err))
  }, [])

  return (
    <AuthProvider>
      <ChatProvider>
        <TooltipProvider>
          <SidebarProvider>
            <AppSidebar />
            <SidebarInset>
              <AppHeader />
              <main className="min-h-0 min-w-0 flex-1">
                <Routes>
                  <Route path="/" element={<Navigate to="/chat" replace />} />
                  <Route path="/about" element={<AboutPage />} />
                  <Route path="/chat" element={<ChatPage />} />
                  {/* Bare /code has no way to know which repo -- redirect to the
                      default one rather than guessing or adding a "no repo
                      selected" empty state nobody would ever actually see. */}
                  <Route path="/code" element={<Navigate to={`/code/${DEFAULT_REPO}`} replace />} />
                  <Route path="/code/:repoName" element={<CodePage />} />
                  {/* Wildcard, not :ref -- refs for non-default branches only
                      resolve as "origin/<name>", which contains a "/" and
                      wouldn't match a single dynamic segment. */}
                  <Route path="/code/:repoName/tree/*" element={<CodePage />} />
                  <Route path="/code/:repoName/commits" element={<CommitsPage />} />
                  <Route path="/code/:repoName/commits/*" element={<CommitsPage />} />
                  <Route path="/code/:repoName/commit/:sha" element={<CommitDetailPage />} />
                  <Route path="/people" element={<PeoplePage />} />
                  <Route path="/people/:id" element={<PersonDetailPage />} />
                </Routes>
              </main>
            </SidebarInset>
          </SidebarProvider>
        </TooltipProvider>
      </ChatProvider>
    </AuthProvider>
  )
}

export default App
