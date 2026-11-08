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
      'editor.background': '#0a1424',
      'diffEditor.insertedLineBackground': '#16a34a0f',
      'diffEditor.insertedTextBackground': '#16a34a1c',
      'diffEditor.removedLineBackground': '#dc26260f',
      'diffEditor.removedTextBackground': '#dc26261c',
    },
  })
}
