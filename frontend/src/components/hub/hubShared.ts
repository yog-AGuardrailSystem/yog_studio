import type { MutableRefObject } from 'react'
import type { ToolGroup } from '../../lib/tools'

/** What the pointer is over right now. Written by the DOM overlay, read by the 3D scene every frame (a ref, not React state). */
export interface HubUi {
  hoverBox: ToolGroup | null
  hoverCard: string | null
}

export const newUi = (): HubUi => ({ hoverBox: null, hoverCard: null })

/** The real <button>/<a> elements that sit over the scene. The scene moves each one onto its projected 3D shape, by key:
 *  `box:<group>` or `card:<toolId>`. */
export type HitMap = Map<string, HTMLElement>
export type HitsRef = MutableRefObject<HitMap>
export type UiRef = MutableRefObject<HubUi>

/** How long the camera takes to fly in, and how long a card takes to fill the screen, before the page changes. */
export const ENTER_MS = 950
