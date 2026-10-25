import Editor, { type OnMount } from '@monaco-editor/react'
import { useEffect, useRef } from 'react'

type Monaco = Parameters<OnMount>[1]
type EditorInstance = Parameters<OnMount>[0]

interface Props {
  value: string
  language?: string
  height?: string
  readOnly?: boolean
  onChange?: (v: string) => void
  /** 1-based lines to highlight (detector evidence). */
  highlightLines?: number[]
  /** Scroll this line into view when it changes. */
  revealLine?: number | null
}

export function CodeView({ value, language = 'python', height = '420px', readOnly = true, onChange, highlightLines = [], revealLine }: Props) {
  const editorRef = useRef<EditorInstance | null>(null)
  const monacoRef = useRef<Monaco | null>(null)
  const decoRef = useRef<{ clear: () => void } | null>(null)

  function applyDecorations() {
    const ed = editorRef.current
    const monaco = monacoRef.current
    if (!ed || !monaco) return
    decoRef.current?.clear()
    decoRef.current = ed.createDecorationsCollection(
      highlightLines.map((n) => ({
        range: new monaco.Range(n, 1, n, 1),
        options: { isWholeLine: true, className: 'evidence-line', linesDecorationsClassName: 'evidence-gutter' },
      })),
    )
  }

  useEffect(applyDecorations, [highlightLines.join(','), value])
  useEffect(() => {
    if (revealLine && editorRef.current) editorRef.current.revealLineInCenter(revealLine)
  }, [revealLine])

  return (
    <div className="overflow-hidden rounded border border-slate-300">
      <Editor
        height={height}
        language={language}
        value={value}
        onChange={(v) => onChange?.(v ?? '')}
        onMount={(ed, monaco) => {
          editorRef.current = ed
          monacoRef.current = monaco
          applyDecorations()
        }}
        options={{ readOnly, minimap: { enabled: false }, fontSize: 13, scrollBeyondLastLine: false, automaticLayout: true }}
      />
    </div>
  )
}
