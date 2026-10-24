import { Component, type ErrorInfo, type ReactNode } from 'react'

export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(error, info)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="rounded border border-red-300 bg-red-50 p-4 text-sm text-red-800" role="alert">
        <b>Something went wrong on this page.</b> {this.state.error.message}
        <div className="mt-2">
          <button
            className="rounded border border-red-300 bg-white px-3 py-1"
            onClick={() => {
              try {
                sessionStorage.clear()
              } catch {
                /* ignore */
              }
              location.reload()
            }}
          >
            Reset the app state and reload
          </button>
        </div>
      </div>
    )
  }
}
