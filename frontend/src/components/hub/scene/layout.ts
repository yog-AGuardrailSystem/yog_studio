// Where things stand and where the camera looks. One shared viewing angle, taken from the reference: a 3/4 view from the
// front-right and above. Every cabinet is parallel, so each one is seen exactly like the reference's single cabinet.
import * as THREE from 'three'
import { boxPlaces } from '../../../lib/hubModel'

/** Cabinet size (world units): long and shallow like the reference, about 3 : 1.2 : 0.55. */
export const CAB = { L: 3.0, D: 1.2, H: 0.55, wall: 0.05, lid: 0.05 }
/** Glass card: landscape, about 1.6 : 1, thin. */
export const CARD = { w: 1.0, h: 0.64, t: 0.018 }
/** How high the card bottoms sit inside the tray, so about 55-60% of each card shows above the rim. */
export const CARD_BASE = 0.2

/** Camera direction: azimuth from the cabinet's front (+z) toward its right end (+x), and elevation. */
export const VIEW = { az: 0.82, el: 0.5 }      // measured from the reference: its long and short faces show at about 2.4 : 1

const dir = new THREE.Vector3(Math.sin(VIEW.az) * Math.cos(VIEW.el), Math.sin(VIEW.el), Math.cos(VIEW.az) * Math.cos(VIEW.el))
/** Unit vector from a target toward the camera. */
export const toCamera = (el = VIEW.el) =>
  new THREE.Vector3(Math.sin(VIEW.az) * Math.cos(el), Math.sin(el), Math.cos(VIEW.az) * Math.cos(el))
/** Screen-right on the floor, for laying the cabinets out side by side as seen from the camera. */
export const RIGHT = new THREE.Vector3(Math.cos(VIEW.az), 0, -Math.sin(VIEW.az))
/** Away from the camera, on the floor. */
export const AWAY = new THREE.Vector3(-dir.x, 0, -dir.z).normalize()

/** World positions of the five cabinets: a row across the screen (desktop) or two columns (phone). */
export function cabinetPositions(count: number, stacked: boolean): THREE.Vector3[] {
  const places = boxPlaces(count, stacked ? 2 : count)
  // boxPlaces gives row units 4.1 apart; the cabinets are seen 3/4, so they need a little more room across the screen.
  const across = stacked ? 0.95 : 0.92, deep = stacked ? 0.95 : 1
  return places.map((p) => RIGHT.clone().multiplyScalar(p.x * across).add(AWAY.clone().multiplyScalar(-p.z * deep)))
}

/** Distance at which a region `w` wide and `h` high (as seen from the camera) fits the screen. */
export function fitDistance(w: number, h: number, fovDeg: number, aspect: number): number {
  const v = THREE.MathUtils.degToRad(fovDeg) / 2
  return Math.max((w / 2) / (Math.tan(v) * aspect), (h / 2) / Math.tan(v))
}
