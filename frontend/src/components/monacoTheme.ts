import type { BeforeMount } from '@monaco-editor/react'

export const YOG_DARK = 'yog-dark'

/**
 * Monaco's built-in "vs-dark" fails WCAG contrast in two places: comments, and the diff editor's
 * bright olive "inserted" highlight behind blue keywords. This theme keeps vs-dark and fixes both.
 */
export const defineYogTheme: BeforeMount = (monaco) => {
  monaco.editor.defineTheme(YOG_DARK, {
    base: 'vs-dark',
    inherit: true,
    rules: [{ token: 'comment', foreground: '8fbf7a' }],
    colors: {
      // black and gold, like the rest of the site
      'editor.background': '#0b0a08',
      'editor.lineHighlightBackground': '#1a17120f',
      'editor.selectionBackground': '#f5b94240',
      'editorCursor.foreground': '#f5b942',
      'editorLineNumber.foreground': '#8f897e',   // 5:1 on the editor background (axe)
      'editorLineNumber.activeForeground': '#f5b942',
      'diffEditor.insertedLineBackground': '#16a34a0f',
      'diffEditor.insertedTextBackground': '#16a34a1c',
      'diffEditor.removedLineBackground': '#dc26260f',
      'diffEditor.removedTextBackground': '#dc26261c',
    },
  })
}
