import { useEffect } from "react"
import { Button } from "@/components/ui/button"

function App() {
  useEffect(() => {
    fetch("http://localhost:8010/ping")
      .then((res) => res.json())
      .then((data) => console.log(data))
      .catch((err) => console.error(err))
  }, [])

  return (
    <div className="flex min-h-svh flex-col items-center justify-center gap-4">
      <h1 className="text-2xl font-semibold">Sabio</h1>
      <p className="text-muted-foreground">Bitcoin protocol intelligence</p>
      <Button>Get started</Button>
    </div>
  )
}

export default App
