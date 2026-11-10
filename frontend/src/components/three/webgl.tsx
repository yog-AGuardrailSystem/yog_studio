import { Component, type ReactNode } from 'react'

/** True when this browser can create a WebGL context (and `?fx=off` has not been asked for). Shared by every 3D scene. */
export function webglOk(): boolean {
  try {
    if (new URLSearchParams(window.location.search).get('fx') === 'off') return false
    const c = document.createElement('canvas')
    return !!(c.getContext('webgl2') || c.getContext('webgl'))
  } catch {
    return false
  }
}

/** Shows `fallback` instead of a 3D scene that threw while rendering. */
export class Boundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children
  }
}
