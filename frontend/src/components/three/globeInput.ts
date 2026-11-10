/** What the pointer is doing over the hero globe. A plain mutable object: the view writes it, the scene reads it every frame
 *  (no React state, so moving the mouse never re-renders anything). Kept out of HeroGlobe.tsx so importing it does not pull in three.js. */
export interface GlobeInput {
  x: number                 // pointer position in CSS px, relative to the globe's box (origin top-left)
  y: number
  inside: boolean
  dragging: boolean
  dragDX: number            // drag in px since the last frame; the scene zeroes these once it has used them
  dragDY: number
  clickId: number           // bumped on every click/tap (not drag); clickX/clickY say where
  clickX: number
  clickY: number
}

export const newInput = (): GlobeInput => ({
  x: 0, y: 0, inside: false, dragging: false, dragDX: 0, dragDY: 0, clickId: 0, clickX: 0, clickY: 0,
})
