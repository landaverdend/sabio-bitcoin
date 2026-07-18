import { loader } from "@monaco-editor/react"
import * as monaco from "monaco-editor"
import EditorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker"

// Self-hosted, not @monaco-editor/react's CDN default (cdn.jsdelivr.net) --
// keeps this fully local and pins the version instead of depending on
// whatever jsdelivr happens to be serving. Only the base editor worker is
// wired up: C++/Python/etc. are all "basic languages" (TextMate-style
// tokenizers, no dedicated worker) in Monaco's terms -- the json/css/html/ts
// workers exist for semantic features (diagnostics, autocomplete) we don't
// need for read-only viewing.
self.MonacoEnvironment = {
  getWorker: () => new EditorWorker(),
}

loader.config({ monaco })
