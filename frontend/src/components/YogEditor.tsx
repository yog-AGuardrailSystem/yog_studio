import Editor, { type OnMount } from '@monaco-editor/react'
import '../lib/monacoSetup'
import { useEffect, useRef } from 'react'
import type { Diagnostic } from '../api/compile'
import { registerYog, YOG_LANG } from '../lib/yogLanguage'
import { defineYogTheme, YOG_DARK } from './monacoTheme'

type EditorInstance = Parameters<OnMount>[0]
type Monaco = Parameters<OnMount>[1]

interface Props {
  value: string
  onChange: (v: string) => void
  diagnostics: Diagnostic[]
  /** lines lit up by "why was this decided?" (deciding clause = strong, supporting facts = soft) */
  decidingLine?: number | null
  supportLines?: number[]
  height?: string
  onReady?: (api: { focusLine: (n: number) => void }) => void
}

const OPTIONS = {
  minimap: { enabled: false }, fontSize: 13, scrollBeyondLastLine: false, automaticLayout: true,
  renderGutterMenu: false, renderFinalNewline: 'on', tabSize: 4, insertSpaces: true, detectIndentation: false, wordWrap: 'on',
  quickSuggestions: { other: true, comments: false, strings: false }, ariaLabel: 'YOG policy editor',
} as never

function beforeMount(m: Parameters<NonNullable<React.ComponentProps<typeof Editor>['beforeMount']>>[0]) {
  defineYogTheme(m)
  registerYog(m)
}

/** The YOG editor: syntax colours, live error markers from the compiler, and trace highlighting. */
export function YogEditor({ value, onChange, diagnostics, decidingLine, supportLines = [], height = '520px', onReady }: Props) {
  const ed = useRef<EditorInstance | null>(null)
  const mon = useRef<Monaco | null>(null)
  const deco = useRef<{ clear: () => void } | null>(null)
  const emitted = useRef<string[]>([])

  // The editor owns its text while you type (a controlled `value` can drop keystrokes when React lags behind fast
  // typing). Outside changes (loading an example, applying a fix) are pushed in as undoable edits.
  useEffect(() => {
    const e = ed.current
    const model = e?.getModel()
    if (!e || !model || model.getValue() === value) return
    if (emitted.current.includes(value)) return // a stale echo of text the user already typed past
    emitted.current = []
    e.executeEdits('external', [{ range: model.getFullModelRange(), text: value, forceMoveMarkers: true }])
    e.pushUndoStop()
  }, [value])

  useEffect(() => {
    const e = ed.current
    const m = mon.current
    const model = e?.getModel()
    if (!e || !m || !model) return
    m.editor.setModelMarkers(
      model,
      'yog',
      diagnostics.map((d) => {
        const line = Math.min(Math.max(d.line ?? 1, 1), model.getLineCount())
        return {
          severity: d.severity === 'error' ? m.MarkerSeverity.Error : m.MarkerSeverity.Warning,
          message: d.message + (d.hint ? `\n${d.hint}` : ''),
          startLineNumber: line, startColumn: d.column ? Math.min(d.column, model.getLineMaxColumn(line)) : 1, endLineNumber: line, endColumn: model.getLineMaxColumn(line),
        }
      }),
    )
  }, [diagnostics, value])

  useEffect(() => {
    const e = ed.current
    const m = mon.current
    if (!e || !m) return
    deco.current?.clear()
    const items = [
      ...supportLines.map((n) => ({ range: new m.Range(n, 1, n, 1), options: { isWholeLine: true, className: 'trace-support-line' } })),
      ...(decidingLine ? [{ range: new m.Range(decidingLine, 1, decidingLine, 1), options: { isWholeLine: true, className: 'trace-deciding-line', linesDecorationsClassName: 'evidence-gutter' } }] : []),
    ]
    deco.current = e.createDecorationsCollection(items)
    if (decidingLine) e.revealLineInCenterIfOutsideViewport(decidingLine)
  }, [decidingLine, supportLines.join(',')])

  return (
    <div className="overflow-hidden rounded border border-slate-300" data-testid="yog-editor">
      <Editor
        height={height}
        language={YOG_LANG}
        theme={YOG_DARK}
        beforeMount={beforeMount}
        defaultValue={value}
        onChange={(v) => { emitted.current = [...emitted.current.slice(-40), v ?? '']; onChange(v ?? '') }}
        onMount={(editor, monaco) => {
          ed.current = editor
          mon.current = monaco
          onReady?.({ focusLine: (n) => { editor.revealLineInCenter(n); editor.setPosition({ lineNumber: n, column: 1 }); editor.focus() } })
        }}
        options={OPTIONS}
      />
    </div>
  )
}
