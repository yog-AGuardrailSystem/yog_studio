import type * as monacoNs from 'monaco-editor'

type Monaco = typeof monacoNs

export const YOG_LANG = 'yog'
let registered = false

const KEYWORDS = ['fact', 'rule', 'allow', 'deny', 'query', 'not']

const SNIPPETS: { label: string; doc: string; body: string }[] = [
  { label: 'fact', doc: 'A piece of ground data', body: 'fact ${1:role}(${2:alice}, ${3:admin})' },
  { label: 'rule', doc: 'A derived predicate', body: 'rule ${1:is_prod}(${2:R}):\n    ${3:environment}(${2:R}, ${4:production})' },
  { label: 'allow', doc: 'A decision that permits', body: 'allow can_${1:action}(${2:Actor}, ${3:Res}):\n    ${4:role}(${2:Actor}, ${5:admin})' },
  { label: 'deny', doc: 'A decision that forbids (DENY beats ALLOW)', body: 'deny can_${1:action}(${2:Actor}, ${3:Res}):\n    ${4:is_prod}(${3:Res})' },
  { label: 'query', doc: 'Ask a question; add "# -> DENY" to make it a test', body: 'query can_${1:action}(${2:alice}, ${3:db1})  # -> ${4:ALLOW}' },
]

/** Registers the YOG language once: tokenizer, completion (keywords, snippets, predicates in the file), hover help. */
export function registerYog(monaco: Monaco): void {
  if (registered) return
  registered = true
  monaco.languages.register({ id: YOG_LANG })
  monaco.languages.setMonarchTokensProvider(YOG_LANG, {
    keywords: KEYWORDS,
    tokenizer: {
      root: [
        [/#.*$/, 'comment'],
        [/"[^"]*"/, 'string'],
        [/\b\d+\b/, 'number'],
        [/==|!=|<=|>=|<|>/, 'operator'],
        [/\b(fact|rule|allow|deny|query|not)\b/, 'keyword'],
        [/\b_\b/, 'variable.predefined'],
        [/\b[A-Z][A-Za-z0-9_]*\b/, 'variable'],
        [/\b[a-z][A-Za-z0-9_]*(?=\()/, 'type.identifier'],
        [/\b[a-z][A-Za-z0-9_]*\b/, 'constant'],
      ],
    },
  } as never)
  monaco.languages.setLanguageConfiguration(YOG_LANG, {
    comments: { lineComment: '#' },
    brackets: [['(', ')']],
    autoClosingPairs: [{ open: '(', close: ')' }, { open: '"', close: '"' }],
    indentationRules: { increaseIndentPattern: /:\s*(#.*)?$/, decreaseIndentPattern: /^\s*$/ },
    onEnterRules: [{ beforeText: /:\s*(#.*)?$/, action: { indentAction: monaco.languages.IndentAction.Indent, appendText: '    ' } }],
  })
  monaco.languages.registerCompletionItemProvider(YOG_LANG, {
    provideCompletionItems(model, position) {
      const word = model.getWordUntilPosition(position)
      const range = { startLineNumber: position.lineNumber, endLineNumber: position.lineNumber, startColumn: word.startColumn, endColumn: word.endColumn }
      const text = model.getValue()
      const preds = Array.from(new Set(Array.from(text.matchAll(/^\s*(?:fact|rule|allow|deny|not)?\s*([a-z][A-Za-z0-9_]*)\(/gm)).map((m) => m[1])))
      const K = monaco.languages.CompletionItemKind
      return {
        suggestions: [
          ...SNIPPETS.map((s) => ({
            label: s.label, kind: K.Snippet, detail: 'YOG: ' + s.doc, insertText: s.body, range,
            insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
          })),
          ...preds.filter((p) => !KEYWORDS.includes(p)).map((p) => ({ label: p, kind: K.Function, detail: 'predicate in this file', insertText: p, range })),
        ],
      }
    },
  })
  const HELP: Record<string, string> = {
    fact: '**fact** states ground data: `fact role(alice, admin)`',
    rule: '**rule** derives a predicate from others (no recursion).',
    allow: '**allow** permits an action when its body holds.',
    deny: '**deny** forbids an action. DENY beats ALLOW; nothing allowed means DENY.',
    query: '**query** asks the engine a question. Add `# -> DENY` to turn it into a test.',
    not: '**not** negates a condition in a body.',
  }
  monaco.languages.registerHoverProvider(YOG_LANG, {
    provideHover(model, pos) {
      const w = model.getWordAtPosition(pos)
      return w && HELP[w.word] ? { contents: [{ value: HELP[w.word] }] } : null
    },
  })
}
