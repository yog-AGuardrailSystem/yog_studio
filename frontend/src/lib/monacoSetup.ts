// Serve Monaco from our own bundle instead of the jsdelivr CDN, so the page needs no third-party script and the
// Content-Security-Policy can say script-src 'self'. Imported once, before any editor mounts (see main.tsx).
import { loader } from '@monaco-editor/react'
import * as monaco from 'monaco-editor'
import EditorWorker from 'monaco-editor/editor/editor.worker?worker'

// Only the base worker: YOG and plaintext need no language service, and python needs just colouring (no worker).
self.MonacoEnvironment = { getWorker: () => new EditorWorker() }
loader.config({ monaco })
