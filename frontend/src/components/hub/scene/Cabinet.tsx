import { useFrame, useThree } from '@react-three/fiber'
import { useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js'
import { GOLD, boxLabel, toolsIn, type HubState } from '../../../lib/hubModel'
import { GROUPS, type ToolGroup } from '../../../lib/tools'
import type { HitsRef, UiRef } from '../hubShared'
import { GlassCard } from './GlassCard'
import { AWAY, CAB, CARD, CARD_BASE } from './layout'
import { engraving, lidGlass, radialGlow, streak } from './textures'
import { MAX_DT, damp, ease, placeHit } from './util'

const { L, D, H, wall, lid: LID } = CAB
const GOLD_C = new THREE.Color(GOLD)
/** Bright light sources go on layer 1, which the main camera sees but the floor mirror does not: in the reference the
 *  reflections are faint, and a mirrored plug would bloom into a hot spot on the floor. */
export const MIRROR_FREE = 1
const noMirror = (o: THREE.Object3D | null) => { o?.layers.set(MIRROR_FREE) }
const PLUG = new THREE.Vector3(L / 2 - wall - 0.07, CARD_BASE + CARD.h * 0.78, -0.12)

// ---- geometry and materials shared by all five cabinets ----
let parts: ReturnType<typeof makeParts> | null = null
function makeParts() {
  const rb = (w: number, h: number, d: number, r = 0.012) => new RoundedBoxGeometry(w, h, d, 3, r)
  const cable = new THREE.CatmullRomCurve3([
    PLUG.clone().add(new THREE.Vector3(0.02, 0, 0)), new THREE.Vector3(L / 2 + 0.12, PLUG.y, PLUG.z),
    new THREE.Vector3(L / 2 + 0.34, 0.05, PLUG.z + 0.1), new THREE.Vector3(L / 2 + 0.9, 0.015, PLUG.z + 0.45),
  ])
  return {
    base: rb(L, wall, D), long: rb(L, H, wall), short: rb(wall, H, D - 2 * wall + 0.002),
    lid: rb(L + 0.02, LID, D + 0.02, 0.014),
    lidGlass: new THREE.PlaneGeometry(L - 0.14, D - 0.14),
    rimLong: new THREE.BoxGeometry(L - 0.01, 0.011, 0.011), rimShort: new THREE.BoxGeometry(0.011, 0.011, D - 0.01),
    hinge: new THREE.CylinderGeometry(0.022, 0.022, 0.16, 16).rotateZ(Math.PI / 2),
    plug: new THREE.CylinderGeometry(0.026, 0.03, 0.1, 16).rotateZ(Math.PI / 2),
    cable: new THREE.TubeGeometry(cable, 40, 0.012, 8, false),
    beam: new THREE.PlaneGeometry(L - 0.75, 0.07),
    engraving: new THREE.PlaneGeometry(L * 0.86, (L * 0.86) * (96 / 2048)),
    leak: new THREE.PlaneGeometry(L - 0.2, D - 0.2),
    pool: new THREE.PlaneGeometry(L * 1.9, D * 3.0),
    shell: new THREE.MeshPhysicalMaterial({ color: '#020202', roughness: 0.45, metalness: 0.1, clearcoat: 1, clearcoatRoughness: 0.22 }),
    inside: new THREE.MeshPhysicalMaterial({ color: '#050504', roughness: 0.6, metalness: 0.1 }),
    lidInner: new THREE.MeshPhysicalMaterial({ map: lidGlass(), roughness: 0.06, metalness: 0.2, clearcoat: 1, clearcoatRoughness: 0.04 }),
    hingeMat: new THREE.MeshStandardMaterial({ color: '#3a2f17', roughness: 0.35, metalness: 0.9 }),
    cableMat: new THREE.MeshStandardMaterial({ color: '#0d0b07', roughness: 0.5, metalness: 0.2, emissive: GOLD_C.clone(), emissiveIntensity: 0.05 }),
  }
}

export interface CabinetProps {
  group: ToolGroup
  at: THREE.Vector3
  state: HubState
  ui: UiRef
  hits: HitsRef
  calm: boolean
  fonts: boolean
  enter: { id: string | null; at: number }
}

/** One stage of the Studio as a black lacquered cabinet: thick walls, a hinged lid with a smoked-glass inside, a gold rim,
 *  engraved lettering on the front, a lit plug at the back-right end, and the stage's tools inside as glass cards. */
export function Cabinet({ group, at, state, ui, hits, calm, fonts, enter }: CabinetProps) {
  const { camera, size } = useThree()
  const p = parts ?? (parts = makeParts())
  const root = useRef<THREE.Group>(null)
  const lidRef = useRef<THREE.Group>(null)
  const a = useRef({ open: 0, hide: 0, hover: 0 })
  const openAmt = useRef(0)
  const isOpen = state.mode !== 'rest' && state.group === group
  const someOpen = state.mode !== 'rest'
  const [mounted, setMounted] = useState(false)
  useEffect(() => {
    if (isOpen) { setMounted(true); return }
    const t = window.setTimeout(() => setMounted(false), 900)
    return () => window.clearTimeout(t)
  }, [isOpen])

  const idx = GROUPS.findIndex((g) => g.id === group) + 1
  const { title } = boxLabel(group)
  const engr = useMemo(() => engraving('YOG STUDIO', `0${idx} ${title.toUpperCase()}`), [idx, title, fonts])
  const mats = useMemo(() => ({
    rim: new THREE.MeshStandardMaterial({ color: '#000', emissive: GOLD_C.clone(), emissiveIntensity: 0.3 }),
    engr: new THREE.MeshBasicMaterial({ map: engr, color: '#e9dcb8', transparent: true, opacity: 0.62, depthWrite: false, toneMapped: false }),
    plug: new THREE.MeshStandardMaterial({ color: '#2b220f', emissive: GOLD_C.clone(), emissiveIntensity: 0.4, metalness: 0.6, roughness: 0.3 }),
    beam: new THREE.MeshBasicMaterial({ map: streak(), color: GOLD_C.clone(), transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false }),
    leak: new THREE.MeshBasicMaterial({ map: radialGlow(), color: GOLD_C.clone(), transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false }),
    pool: new THREE.MeshBasicMaterial({ map: radialGlow(), color: GOLD_C.clone(), transparent: true, opacity: 0.05, blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false }),
  }), [engr])
  useEffect(() => () => { for (const m of Object.values(mats)) m.dispose(); engr.dispose() }, [mats, engr])

  const hitMin = useMemo(() => new THREE.Vector3(-L / 2, 0, -D / 2), [])
  const hitMax = useMemo(() => new THREE.Vector3(L / 2, H + LID, D / 2), [])

  useFrame((_, dtRaw) => {
    const r = root.current, l = lidRef.current
    if (!r || !l) return
    const dt = Math.min(dtRaw, MAX_DT), k = calm ? 80 : 1, t = a.current
    t.open = damp(t.open, isOpen ? 1 : 0, (isOpen ? 1.9 : 3.5) * k, dt)
    t.hide = damp(t.hide, someOpen && !isOpen ? 1 : 0, 2.6 * k, dt)
    t.hover = damp(t.hover, ui.current.hoverBox === group && !someOpen ? 1 : 0, 7 * k, dt)
    openAmt.current = t.open
    r.position.copy(at).addScaledVector(AWAY, t.hide * 9)
    r.position.y = t.hover * 0.05
    r.visible = t.hide < 0.98
    // the lid swings on its hinges: a crack on hover, ~100° with a small overshoot when opened
    l.rotation.x = -(1.78 * ease.outBack(Math.min(1, t.open * 1.05)) + t.hover * 0.15)
    mats.rim.emissiveIntensity = 0.3 + t.hover * 0.5 + t.open * 0.15
    mats.engr.opacity = 0.55 + t.hover * 0.35
    mats.leak.opacity = t.hover * 0.55 + t.open * 0.2
    const pulse = calm ? 1 : 0.85 + Math.sin(performance.now() / 700) * 0.15
    mats.beam.opacity = Math.max(0, t.open - 0.55) / 0.45 * 0.75 * pulse
    mats.plug.emissiveIntensity = 0.3 + t.open * 1.6 * pulse
    mats.pool.opacity = 0.05 + t.hover * 0.06 + t.open * 0.05
    r.updateMatrixWorld(true)
    placeHit(hits.current.get(`box:${group}`), r, hitMin, hitMax, camera, size.width, size.height, !someOpen && t.hide < 0.5)
  })

  return (
    <group ref={root} position={at}>
      {/* tray: base, two long walls, two short walls with real thickness */}
      <mesh geometry={p.base} material={p.shell} position={[0, wall / 2, 0]} />
      <mesh geometry={p.long} material={p.shell} position={[0, H / 2, D / 2 - wall / 2]} />
      <mesh geometry={p.long} material={p.shell} position={[0, H / 2, -D / 2 + wall / 2]} />
      <mesh geometry={p.short} material={p.shell} position={[L / 2 - wall / 2, H / 2, 0]} />
      <mesh geometry={p.short} material={p.shell} position={[-L / 2 + wall / 2, H / 2, 0]} />
      <mesh geometry={p.leak} material={p.inside} position={[0, wall + 0.001, 0]} rotation={[-Math.PI / 2, 0, 0]} />
      {/* light catching the top edges of the walls */}
      <mesh geometry={p.rimLong} material={mats.rim} position={[0, H, D / 2]} />
      <mesh geometry={p.rimLong} material={mats.rim} position={[0, H, -D / 2]} />
      <mesh geometry={p.rimShort} material={mats.rim} position={[L / 2, H, 0]} />
      <mesh geometry={p.rimShort} material={mats.rim} position={[-L / 2, H, 0]} />
      {/* engraved lettering on the front */}
      <mesh geometry={p.engraving} material={mats.engr} position={[0, H * 0.48, D / 2 + 0.0015]} />
      {/* light inside: leaks out of the gap on hover, fills the tray when open */}
      <mesh ref={noMirror} geometry={p.leak} material={mats.leak} position={[0, wall + 0.01, 0]} rotation={[-Math.PI / 2, 0, 0]} />
      {/* hinges on the back edge */}
      <mesh geometry={p.hinge} material={p.hingeMat} position={[-L * 0.3, H + 0.005, -D / 2 - 0.012]} />
      <mesh geometry={p.hinge} material={p.hingeMat} position={[L * 0.3, H + 0.005, -D / 2 - 0.012]} />
      {/* lid on its hinge line */}
      <group ref={lidRef} position={[0, H, -D / 2 - 0.01]}>
        <mesh geometry={p.lid} material={p.shell} position={[0, LID / 2, D / 2 + 0.01]} />
        <mesh geometry={p.lidGlass} material={p.lidInner} position={[0, -0.001, D / 2 + 0.01]} rotation={[Math.PI / 2, 0, 0]} />
        <mesh geometry={p.rimLong} material={mats.rim} position={[0, LID, D + 0.02]} />
        <mesh geometry={p.rimShort} material={mats.rim} position={[L / 2 + 0.01, LID, D / 2 + 0.01]} />
      </group>
      {/* the lit plug and its cable at the back-right end, and the beam it throws across the cards */}
      <mesh geometry={p.plug} material={mats.plug} position={PLUG} ref={noMirror} />
      <mesh geometry={p.cable} material={p.cableMat} />
      <mesh ref={noMirror} geometry={p.beam} material={mats.beam} position={[PLUG.x - (L - 0.75) / 2, PLUG.y + 0.02, PLUG.z + 0.02]} rotation={[0, 0, 0.04]} />
      {/* soft gold pool on the floor */}
      <mesh ref={noMirror} geometry={p.pool} material={mats.pool} position={[0, 0.003, 0.1]} rotation={[-Math.PI / 2, 0, 0]} />
      {mounted && toolsIn(group).map((tool, i, all) => (
        <GlassCard key={tool.id} toolId={tool.id} group={group} index={i} count={all.length} openAmt={openAmt}
          enter={enter} cabinet={root} ui={ui} hits={hits} calm={calm} fonts={fonts} />
      ))}
    </group>
  )
}
