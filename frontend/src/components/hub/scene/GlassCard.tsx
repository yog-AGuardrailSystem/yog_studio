import { useFrame, useThree } from '@react-three/fiber'
import { useEffect, useMemo, useRef, type RefObject } from 'react'
import * as THREE from 'three'
import { GOLD, accentFor, cardIndex, toolsIn } from '../../../lib/hubModel'
import type { ToolGroup } from '../../../lib/tools'
import type { HitsRef, UiRef } from '../hubShared'
import { CAB, CARD, CARD_BASE } from './layout'
import { cardFace, streak } from './textures'
import { MAX_DT, damp, ease, placeHit } from './util'

/** Card slots along the tray's long axis; the right end is left free for the plug, like the reference. */
export function slotX(i: number, n: number): number {
  const x0 = -CAB.L / 2 + 0.42, x1 = CAB.L / 2 - 0.62
  return n === 1 ? (x0 + x1) / 2 : x0 + (i / (n - 1)) * (x1 - x0)
}
const LEAN = 0.12                        // cards lean back a little, like files resting in a drawer
const Q_FACE = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), Math.PI / 2)   // face the cabinet's right end
const WHITE = new THREE.Color('#ffffff')
const GOLD_C = new THREE.Color(GOLD)
const REST_GLASS = new THREE.Color('#15120b')
const MIN = new THREE.Vector3(-CARD.w / 2, 0, -CARD.t)
const MAX = new THREE.Vector3(CARD.w / 2, CARD.h, CARD.t)

let shared: { geo: THREE.ExtrudeGeometry; decal: THREE.PlaneGeometry; streak: THREE.PlaneGeometry } | null = null
function geometry() {
  if (shared) return shared
  const { w, h, t } = CARD, r = 0.045, x = -w / 2
  const s = new THREE.Shape()
  s.moveTo(x + r, 0); s.lineTo(x + w - r, 0); s.quadraticCurveTo(x + w, 0, x + w, r)
  s.lineTo(x + w, h - r); s.quadraticCurveTo(x + w, h, x + w - r, h)
  s.lineTo(x + r, h); s.quadraticCurveTo(x, h, x, h - r)
  s.lineTo(x, r); s.quadraticCurveTo(x, 0, x + r, 0)
  const geo = new THREE.ExtrudeGeometry(s, { depth: t, bevelEnabled: true, bevelThickness: 0.004, bevelSize: 0.004, bevelSegments: 2, curveSegments: 8 })
  geo.translate(0, 0, -t / 2)
  shared = { geo, decal: new THREE.PlaneGeometry(w * 0.97, h * 0.97), streak: new THREE.PlaneGeometry(w * 0.9, h * 0.32) }
  return shared
}

export interface CardProps {
  toolId: string
  group: ToolGroup
  index: number
  count: number
  /** 0..1, how far the cabinet has opened; cards rise in one after another as it passes their turn. */
  openAmt: RefObject<number>
  /** Card being entered (clicked) in this cabinet, and when the click happened (performance.now()). */
  enter: { id: string | null; at: number }
  cabinet: RefObject<THREE.Group | null>
  ui: UiRef
  hits: HitsRef
  calm: boolean
  fonts: boolean
}

/** One tool as a thin glass card standing in the open cabinet: rises into its slot, lifts and lights in its accent colour
 *  on hover, and on click rises out of the slot, turns to the camera and flies forward. */
export function GlassCard({ toolId, group, index, count, openAmt, enter, cabinet, ui, hits, calm, fonts }: CardProps) {
  const { camera, size } = useThree()
  const root = useRef<THREE.Group>(null)
  const g = geometry()
  const accent = useMemo(() => new THREE.Color(accentFor(toolId)), [toolId])
  const tool = useMemo(() => toolsIn(group)[index], [group, index])
  const face = useMemo(() => new THREE.MeshPhysicalMaterial({ color: REST_GLASS, roughness: 0.14, metalness: 0.15, clearcoat: 1, clearcoatRoughness: 0.08, transparent: true, opacity: 0.9, emissive: new THREE.Color(0, 0, 0) }), [])
  const rim = useMemo(() => new THREE.MeshStandardMaterial({ color: '#1a1408', roughness: 0.3, metalness: 0.6, emissive: GOLD_C.clone(), emissiveIntensity: 0.55 }), [])
  const decalTex = useMemo(() => cardFace(cardIndex(group, tool.id), tool.name, tool.id), [group, tool, fonts])     // fonts: redraw once loaded
  const decal = useMemo(() => new THREE.MeshBasicMaterial({ map: decalTex, color: GOLD_C.clone(), transparent: true, opacity: 0.9, depthWrite: false, toneMapped: false }), [decalTex])
  const glow = useMemo(() => new THREE.MeshBasicMaterial({ map: streak(), color: GOLD_C.clone(), transparent: true, opacity: 0.28, blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false }), [])
  useEffect(() => () => { face.dispose(); rim.dispose(); decal.dispose(); decalTex.dispose(); glow.dispose() }, [face, rim, decal, decalTex, glow])

  const a = useRef({ appear: 0, hover: 0, dim: 0 })
  const slot = useMemo(() => ({
    pos: new THREE.Vector3(slotX(index, count), CARD_BASE, 0),
    quat: new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), LEAN).multiply(Q_FACE),
  }), [index, count])
  const tmp = useMemo(() => ({ p: new THREE.Vector3(), q: new THREE.Quaternion(), wq: new THREE.Quaternion(), tp: new THREE.Vector3(), tq: new THREE.Quaternion(), fwd: new THREE.Vector3() }), [])

  useFrame((_, dtRaw) => {
    const r = root.current
    if (!r) return
    const dt = Math.min(dtRaw, MAX_DT), k = calm ? 80 : 1, t = a.current
    // rise into the slot in turn as the lid opens
    const turn = 0.5 + index * 0.07
    t.appear = damp(t.appear, (openAmt.current ?? 0) > turn ? 1 : 0, 7 * k, dt)
    const mine = enter.id === toolId, other = !!enter.id && !mine
    t.hover = damp(t.hover, ui.current.hoverCard === toolId || mine ? 1 : 0, 10 * k, dt)
    t.dim = damp(t.dim, other ? 1 : 0, 6 * k, dt)

    // pose in the slot (cabinet-local)
    tmp.p.copy(slot.pos)
    tmp.p.y += (1 - ease.outCubic(t.appear)) * -(CARD.h + 0.1) + t.hover * CARD.h * 0.12
    tmp.q.copy(slot.quat)
    let scale = 1, flight = 0
    if (mine) {
      const e = calm ? 1 : Math.min(1, (performance.now() - enter.at) / 900)
      const lift = ease.outCubic(Math.min(1, e / 0.38))              // 1) straight up out of the slot
      tmp.p.y += lift * CARD.h * 1.05
      const fly = ease.inOutCubic(Math.max(0, (e - 0.38) / 0.62))    // 2) turn to the camera and come forward
      if (fly > 0 && cabinet.current) {
        const cab = cabinet.current
        const dist = 2.0
        camera.getWorldDirection(tmp.fwd)
        tmp.tp.copy(camera.position).addScaledVector(tmp.fwd, dist)
        tmp.tp.y -= CARD.h * 0.5 * fillScale(dist)
        cab.worldToLocal(tmp.tp)
        cab.getWorldQuaternion(tmp.wq)
        tmp.tq.copy(tmp.wq).invert().multiply(camera.quaternion)
        tmp.p.lerp(tmp.tp, fly)
        tmp.q.slerp(tmp.tq, fly)
        scale = 1 + (fillScale(dist) - 1) * fly
        flight = fly
      }
    }
    r.position.copy(tmp.p)
    r.quaternion.copy(tmp.q)
    r.scale.setScalar(scale)
    r.visible = t.appear > 0.01

    // colour: gold glass at rest; the card's accent when lit; the others dim while one is chosen
    const lit = t.hover
    // in flight the card becomes solid deep colour with a crisp title, like the reference (no see-through, less glow)
    face.color.copy(REST_GLASS).lerp(accent.clone().multiplyScalar(0.55), lit).lerp(accent.clone().multiplyScalar(0.3), flight).multiplyScalar(1 - t.dim * 0.6)
    face.emissive.copy(accent).multiplyScalar(lit * 0.42 * (1 - flight * 0.75))
    face.opacity = 0.9 + flight * 0.1
    rim.emissive.copy(GOLD_C).lerp(accent, lit)
    rim.emissiveIntensity = (0.55 + lit * 1.0) * (1 - t.dim * 0.75)
    decal.color.copy(GOLD_C).lerp(WHITE, lit).lerp(accent.clone().lerp(WHITE, 0.25).multiplyScalar(1.3), flight)   // in flight: title bright in the card colour, like the reference
    decal.opacity = (0.9 + flight * 0.1) * (1 - t.dim * 0.6)
    glow.opacity = (0.28 + lit * 0.2) * (1 - t.dim) * (1 - flight)
    glow.color.copy(GOLD_C).lerp(accent, lit)

    r.updateMatrixWorld(true)
    placeHit(hits.current.get(`card:${toolId}`), r, MIN, MAX, camera, size.width, size.height, t.appear > 0.05 && !enter.id)
  })

  // how much bigger the card must be, `dist` in front of the camera, to fill ~70% of the screen width
  function fillScale(dist: number) {
    const cam = camera as THREE.PerspectiveCamera
    const visibleW = 2 * dist * Math.tan(THREE.MathUtils.degToRad(cam.fov) / 2) * (size.width / Math.max(1, size.height))
    return Math.min(0.7 * visibleW, 1.7 * 2 * dist * Math.tan(THREE.MathUtils.degToRad(cam.fov) / 2)) / CARD.w
  }

  return (
    <group ref={root}>
      <mesh geometry={g.geo} material={[face, rim]} renderOrder={1} />
      <mesh geometry={g.decal} material={decal} position={[0, CARD.h / 2, CARD.t / 2 + 0.006]} renderOrder={2} />
      <mesh ref={(o) => { o?.layers.set(1) }} geometry={g.streak} material={glow} position={[CARD.w * 0.04, CARD.h * 0.78, CARD.t / 2 + 0.008]} rotation={[0, 0, -0.12]} renderOrder={3} />
    </group>
  )
}
