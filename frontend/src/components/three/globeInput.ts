/** What the pointer is doing over the hero globe. A plain mutable object: the view writes it, the scene reads it every frame
 *  (no React state, so moving the mouse never re-renders anything). Kept out of HeroGlobe.tsx so importing it does not pull in three.js. */
export interface GlobeInput {
  x: number                 // pointer over the host, -1..1 (right is +)
  y: number                 // -1..1 (up is +)
  inside: boolean
  enteredAt: number         // seconds (performance.now()/1000) when the pointer came in
  dragging: boolean
  dragDX: number            // drag since the last frame, as a fraction of the host width
  dragDY: number
  clickAt: number           // seconds of the last click/tap/keyboard request, -1 if none
}

export const newInput = (): GlobeInput => ({ x: 0, y: 0, inside: false, enteredAt: 0, dragging: false, dragDX: 0, dragDY: 0, clickAt: -1 })
