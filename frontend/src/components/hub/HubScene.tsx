// The 3D half of the Studio hub. Heavy (three.js), so it is only ever loaded through HubStageView.
// It draws five boxes, the cards of the open box, dust and a camera that flies to the open box. It never handles clicks:
// each frame it moves the real DOM buttons (see HubOverlay) onto the projected rectangle of the shape they stand for.
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { ACCENTS, GOLD, accentFor, boxLabel, boxPlaces, cardIndex, cardSlots, toolsIn, type HubState } from '../../lib/hubModel'
import { GROUPS, type ToolGroup } from '../../lib/tools'
import type { HitsRef, UiRef } from './hubShared'

// ---- sizes (world units) ----
const TRAY = { w: 3.2, h: 1.0, d: 2.0 }
const CARD = { w: 0.6, h: 1.0 }

const damp = (a: number, b: number, lambda: number, dt: number) => a + (b - a) * (1 - Math.exp(-lambda * dt))

// ---- shared geometry and materials (created once, never per frame) ----
function rounded(w: number, h: number, r: number): THREE.Shape {
  const s = new THREE.Shape()
  const x = -w / 2
  s.moveTo(x + r, 0)
  s.lineTo(x + w - r, 0); s.quadraticCurveTo(x + w, 0, x + w, r)
  s.lineTo(x + w, h - r); s.quadraticCurveTo(x + w, h, x + w - r, h)
  s.lineTo(x + r, h); s.quadraticCurveTo(x, h, x, h - r)
  s.lineTo(x, r); s.quadraticCurveTo(x, 0, x + r, 0)
  return s
}

function useFontsReady(): boolean {
  const [ok, setOk] = useState(false)
  useEffect(() => {
    let alive = true
    const done = () => { if (alive) setOk(true) }
    if ('fonts' in document) {
      Promise.all([document.fonts.load('600 40px "Inter Tight"'), document.fonts.load('500 20px "JetBrains Mono"')]).catch(() => undefined).then(done)
    } else done()
    const t = window.setTimeout(done, 1500)                  // never wait forever for a font
    return () => { alive = false; window.clearTimeout(t) }
  }, [])
  return ok
}

function canvasTexture(w: number, h: number, draw: (g: CanvasRenderingContext2D) => void): THREE.CanvasTexture {
  const c = document.createElement('canvas')
  c.width = w; c.height = h
  const g = c.getContext('2d')!
  draw(g)
  const t = new THREE.CanvasTexture(c)
  t.colorSpace = THREE.SRGBColorSpace
  t.anisotropy = 4
  return t
}

function wrap(g: CanvasRenderingContext2D, text: string, maxW: number): string[] {
  const words = text.split(' ')
  const lines: string[] = []
  let line = ''
  for (const w of words) {
    const t = line ? `${line} ${w}` : w
    if (g.measureText(t).width > maxW && line) { lines.push(line); line = w } else line = t
  }
  if (line) lines.push(line)
  return lines
}

// ---- projection of a 3D shape to a DOM rectangle ----
const _v = new THREE.Vector3()
function place(el: HTMLElement | undefined, obj: THREE.Object3D, min: THREE.Vector3, max: THREE.Vector3, camera: THREE.Camera, w: number, h: number, show: boolean) {
  if (!el) return
  if (!show) { if (el.style.display !== 'none') el.style.display = 'none'; return }
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity
  for (let i = 0; i < 8; i++) {
    _v.set(i & 1 ? max.x : min.x, i & 2 ? max.y : min.y, i & 4 ? max.z : min.z).applyMatrix4(obj.matrixWorld).project(camera)
    const sx = (_v.x * 0.5 + 0.5) * w, sy = (-_v.y * 0.5 + 0.5) * h
    x0 = Math.min(x0, sx); x1 = Math.max(x1, sx); y0 = Math.min(y0, sy); y1 = Math.max(y1, sy)
  }
  const s = el.style
  if (s.display === 'none') s.display = ''
  const t = `translate3d(${x0.toFixed(1)}px, ${y0.toFixed(1)}px, 0)`
  if (s.transform !== t) s.transform = t
  const ww = `${Math.max(0, x1 - x0).toFixed(1)}px`, hh = `${Math.max(0, y1 - y0).toFixed(1)}px`
  if (s.width !== ww) s.width = ww
  if (s.height !== hh) s.height = hh
}

interface Common { state: HubState; ui: UiRef; hits: HitsRef; calm: boolean }

// ---- one card ----
function Card({ toolId, group, index, count, openAmt, enterId, fonts, ui, hits, calm }: Pick<Common, 'ui' | 'hits' | 'calm'> & {
  toolId: string; group: ToolGroup; index: number; count: number; openAmt: React.RefObject<number>; enterId: string | null; fonts: boolean
}) {
  const { camera, size } = useThree()
  const root = useRef<THREE.Group>(null)
  const face = useRef<THREE.MeshStandardMaterial>(null)
  const text = useRef<THREE.MeshBasicMaterial>(null)
  const glow = useRef<THREE.MeshBasicMaterial>(null)
  const edge = useRef<THREE.LineBasicMaterial>(null)
  const a = useRef({ appear: 0, hover: 0, enter: 0 })
  const accent = useMemo(() => new THREE.Color(accentFor(toolId)), [toolId])
  const gold = useMemo(() => new THREE.Color(GOLD), [])
  const slot = useMemo(() => cardSlots(count)[index], [count, index])
  const tool = useMemo(() => toolsIn(group)[index], [group, index])
  const shape = useMemo(() => rounded(CARD.w, CARD.h, 0.05), [])
  const faceGeo = useMemo(() => new THREE.ShapeGeometry(shape), [shape])
  const edgeGeo = useMemo(() => new THREE.BufferGeometry().setFromPoints(shape.getPoints(10).map((p) => new THREE.Vector3(p.x, p.y, 0.002))), [shape])
  const tex = useMemo(() => canvasTexture(256, 416, (g) => {
    g.clearRect(0, 0, 256, 416)
    g.fillStyle = '#fff'
    g.font = '500 30px "JetBrains Mono", ui-monospace, monospace'
    g.textBaseline = 'top'
    g.fillText(cardIndex(group, tool.id), 22, 394 - 340)
    g.font = '600 38px "Inter Tight", Inter, system-ui, sans-serif'
    const lines = wrap(g, tool.name, 212)
    lines.slice(0, 3).forEach((l, i) => g.fillText(l, 22, 394 - 340 + 50 + i * 44))
    g.fillRect(22, 392 - 12, 40, 3)                          // a short rule at the bottom, like the reference
  }), [group, tool, fonts])
  useEffect(() => () => { tex.dispose(); faceGeo.dispose(); edgeGeo.dispose() }, [tex, faceGeo, edgeGeo])

  useFrame((_, dtRaw) => {
    const dt = Math.min(dtRaw, 0.05), k = calm ? 80 : 1
    const g = root.current
    if (!g) return
    const hovered = ui.current.hoverCard === toolId
    const entering = enterId === toolId
    const t = a.current
    t.appear = damp(t.appear, openAmt.current >= 0.85 ? 1 : 0, (openAmt.current >= 0.85 ? 5 - index * 0.35 : 7) * k, dt)
    t.hover = damp(t.hover, hovered || entering ? 1 : 0, 9 * k, dt)
    t.enter = damp(t.enter, entering ? 1 : 0, 6 * k, dt)
    const rise = (1 - t.appear) * -0.85 + t.hover * 0.3
    g.position.set(slot.x, 0.55 + rise + t.enter * 0.9, slot.z + 0.12 + t.enter * 2.4)
    g.rotation.x = -slot.lean * (1 - t.enter * 0.9) - t.hover * 0.06
    g.scale.setScalar(1 + t.enter * 1.5)
    g.visible = t.appear > 0.01
    const c = face.current, tx = text.current, gl = glow.current, ed = edge.current
    if (c) { c.color.set('#15110a').lerp(accent.clone().multiplyScalar(0.55), t.hover); c.emissive.copy(accent).multiplyScalar(t.hover * 0.35) }
    if (tx) tx.color.copy(gold).lerp(WHITE, t.hover)
    if (ed) ed.color.copy(gold).lerp(accent, t.hover)
    if (gl) { gl.color.copy(accent) }
    if (gl) gl.opacity = t.hover * 0.8
    g.updateMatrixWorld(true)
    place(hits.current.get(`card:${toolId}`), g, MIN_CARD, MAX_CARD, camera, size.width, size.height, t.appear > 0.05)
  })

  return (
    <group ref={root}>
      <mesh geometry={faceGeo}>
        <meshStandardMaterial ref={face} color="#15110a" metalness={0.55} roughness={0.32} side={THREE.DoubleSide} />
      </mesh>
      <lineLoop geometry={edgeGeo}><lineBasicMaterial ref={edge} color={GOLD} toneMapped={false} /></lineLoop>
      <mesh position={[0, CARD.h * 0.5, 0.004]} renderOrder={2}>
        <planeGeometry args={[CARD.w, CARD.w * (416 / 256)]} />
        <meshBasicMaterial ref={text} map={tex} transparent color={GOLD} toneMapped={false} depthWrite={false} />
      </mesh>
      <mesh position={[0, CARD.h * 0.5, -0.03]} scale={[2.6, 2.0, 1]}>
        <planeGeometry args={[CARD.w, CARD.h]} />
        <meshBasicMaterial ref={glow} map={floorPool()} color={ACCENTS[0]} transparent opacity={0} blending={THREE.AdditiveBlending} depthWrite={false} toneMapped={false} />
      </mesh>
    </group>
  )
}
const WHITE = new THREE.Color('#ffffff')
const MIN_CARD = new THREE.Vector3(-CARD.w / 2, 0, 0)
const MAX_CARD = new THREE.Vector3(CARD.w / 2, CARD.h, 0.01)

// ---- one box ----
function Box({ group, placeAt, state, ui, hits, calm, fonts }: Common & {
  group: ToolGroup; placeAt: { x: number; z: number; yaw: number }; fonts: boolean
}) {
  const { camera, size } = useThree()
  const root = useRef<THREE.Group>(null)
  const lid = useRef<THREE.Group>(null)
  const edge = useRef<THREE.LineBasicMaterial>(null)
  const a = useRef({ open: 0, hide: 0, hover: 0 })
  const openAmt = useRef(0)
  const isOpen = state.mode !== 'rest' && state.group === group
  const someOpen = state.mode !== 'rest'
  const enterId = state.mode === 'enter' && state.group === group ? state.tool : null
  const [mounted, setMounted] = useState(false)
  useEffect(() => {
    if (isOpen) { setMounted(true); return }
    const t = window.setTimeout(() => setMounted(false), 800)
    return () => window.clearTimeout(t)
  }, [isOpen])

  const body = useMemo(() => {
    const g = new THREE.BoxGeometry(TRAY.w, TRAY.h, TRAY.d)
    return { g, e: new THREE.EdgesGeometry(g) }
  }, [])
  const lidGeo = useMemo(() => {
    const g = new THREE.BoxGeometry(TRAY.w + 0.04, 0.07, TRAY.d + 0.04)
    g.translate(0, 0.035, TRAY.d / 2 + 0.02)               // hinge on the back edge
    return { g, e: new THREE.EdgesGeometry(g) }
  }, [])
  const { title, count } = boxLabel(group)
  const idx = GROUPS.findIndex((g) => g.id === group) + 1
  const label = useMemo(() => canvasTexture(1024, 160, (g) => {
    g.clearRect(0, 0, 1024, 160)
    g.fillStyle = '#fff'
    g.textBaseline = 'middle'
    g.font = '500 44px "JetBrains Mono", ui-monospace, monospace'
    g.fillText(`0${idx}`, 40, 80)
    g.font = '600 64px "Inter Tight", Inter, system-ui, sans-serif'
    g.fillText(title.toUpperCase(), 150, 80)
    g.font = '500 40px "JetBrains Mono", ui-monospace, monospace'
    g.textAlign = 'right'
    g.fillText(`${count} TOOLS`, 984, 80)
  }), [title, count, idx, fonts])
  useEffect(() => () => { body.g.dispose(); body.e.dispose(); lidGeo.g.dispose(); lidGeo.e.dispose(); label.dispose() }, [body, lidGeo, label])

  useFrame((_, dtRaw) => {
    const dt = Math.min(dtRaw, 0.05), k = calm ? 80 : 1
    const r = root.current, l = lid.current
    if (!r || !l) return
    const t = a.current
    t.open = damp(t.open, isOpen ? 1 : 0, 3.4 * k, dt)
    t.hide = damp(t.hide, someOpen && !isOpen ? 1 : 0, 3.2 * k, dt)
    t.hover = damp(t.hover, ui.current.hoverBox === group && !someOpen ? 1 : 0, 8 * k, dt)
    openAmt.current = t.open
    const bob = calm ? 0 : Math.sin(performance.now() / 1300 + placeAt.x) * 0.025
    r.position.set(placeAt.x * (1 + t.hide * 0.9), t.hover * 0.1 + bob - t.hide * 1.4, placeAt.z - t.hide * 6)
    r.rotation.y = placeAt.yaw * (1 - t.open)
    r.visible = t.hide < 0.97
    l.rotation.x = -(t.open * 1.85 + t.hover * 0.16)
    if (edge.current) edge.current.opacity = 0.55 + t.hover * 0.45 + t.open * 0.2
    r.updateMatrixWorld(true)
    if (!someOpen) place(hits.current.get(`box:${group}`), r, MIN_BOX, MAX_BOX, camera, size.width, size.height, t.hide < 0.5)
  })

  return (
    <group ref={root} position={[placeAt.x, 0, placeAt.z]}>
      <group position={[0, TRAY.h / 2, 0]}>
        <mesh geometry={body.g}><meshStandardMaterial color="#0c0b09" metalness={0.35} roughness={0.55} /></mesh>
        <lineSegments geometry={body.e}><lineBasicMaterial ref={edge} color={GOLD} transparent opacity={0.6} toneMapped={false} /></lineSegments>
      </group>
      {/* the tool cards stand inside the tray; the tray's own front wall hides their lower part */}
      {mounted && (
        <group>
          {toolsIn(group).map((t, i, all) => (
            <Card key={t.id} toolId={t.id} group={group} index={i} count={all.length} openAmt={openAmt} enterId={enterId} fonts={fonts}
              ui={ui} hits={hits} calm={calm} />
          ))}
        </group>
      )}
      <group ref={lid} position={[0, TRAY.h, -TRAY.d / 2 - 0.02]}>
        <mesh geometry={lidGeo.g}><meshStandardMaterial color="#100e0a" metalness={0.4} roughness={0.5} /></mesh>
        <lineSegments geometry={lidGeo.e}><lineBasicMaterial color={GOLD} transparent opacity={0.7} toneMapped={false} /></lineSegments>
      </group>
      <mesh position={[0, TRAY.h * 0.5, TRAY.d / 2 + 0.004]}>
        <planeGeometry args={[TRAY.w * 0.86, (TRAY.w * 0.86) * (160 / 1024)]} />
        <meshBasicMaterial map={label} transparent color={GOLD} toneMapped={false} depthWrite={false} />
      </mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.004, 0]}>
        <planeGeometry args={[6.4, 5.0]} />
        <meshBasicMaterial map={floorPool()} color={GOLD} transparent opacity={0.5} blending={THREE.AdditiveBlending} depthWrite={false} toneMapped={false} />
      </mesh>
    </group>
  )
}
const MIN_BOX = new THREE.Vector3(-TRAY.w / 2, 0, -TRAY.d / 2)
const MAX_BOX = new THREE.Vector3(TRAY.w / 2, TRAY.h + 0.15, TRAY.d / 2)

// a soft white radial glow, tinted gold on the floor and by the accent colour behind a hovered card; one texture shared by all
let pool: THREE.CanvasTexture | null = null
function floorPool(): THREE.CanvasTexture {
  if (!pool) {
    pool = canvasTexture(128, 128, (g) => {
      const r = g.createRadialGradient(64, 64, 4, 64, 64, 62)
      r.addColorStop(0, 'rgba(255,255,255,0.34)'); r.addColorStop(0.5, 'rgba(255,255,255,0.09)'); r.addColorStop(1, 'rgba(255,255,255,0)')
      g.fillStyle = r; g.fillRect(0, 0, 128, 128)
    })
  }
  return pool
}

// ---- floating dust ----
function Dust({ n, calm }: { n: number; calm: boolean }) {
  const pts = useRef<THREE.Points>(null)
  const geo = useMemo(() => {
    const g = new THREE.BufferGeometry()
    const p = new Float32Array(n * 3)
    for (let i = 0; i < n; i++) { p[i * 3] = (Math.random() - 0.5) * 26; p[i * 3 + 1] = Math.random() * 5; p[i * 3 + 2] = -9 + Math.random() * 14 }
    g.setAttribute('position', new THREE.BufferAttribute(p, 3))
    return g
  }, [n])
  useEffect(() => () => geo.dispose(), [geo])
  useFrame((_, dt) => { if (!calm && pts.current) { pts.current.position.y = Math.sin(performance.now() / 4000) * 0.25; pts.current.rotation.y += dt * 0.01 } })
  return <points ref={pts} geometry={geo}><pointsMaterial color={GOLD} size={0.045} transparent opacity={0.7} sizeAttenuation depthWrite={false} toneMapped={false} /></points>
}

// ---- the camera: wide over all five boxes, close over the open one, then closer still on the chosen card ----
function Rig({ state, places, calm }: { state: HubState; places: { x: number; z: number }[]; calm: boolean }) {
  const { camera, size } = useThree()
  const cur = useRef<{ pos: THREE.Vector3; look: THREE.Vector3 } | null>(null)
  const want = useMemo(() => ({ pos: new THREE.Vector3(), look: new THREE.Vector3() }), [])
  useFrame((_, dtRaw) => {
    const dt = Math.min(dtRaw, 0.05)
    const cam = camera as THREE.PerspectiveCamera
    const aspect = size.width / Math.max(1, size.height)
    const fovV = THREE.MathUtils.degToRad(cam.fov)
    const tanH = Math.tan(fovV / 2) * aspect, tanV = Math.tan(fovV / 2)
    const fit = (w: number, d: number) => Math.max((w / 2) / tanH, (d / 2) / tanV)
    if (state.mode === 'rest') {
      const xs = places.map((p) => p.x), zs = places.map((p) => p.z)
      const w = Math.max(...xs) - Math.min(...xs) + TRAY.w + (new Set(xs).size <= 2 ? 2.4 : 0.9)
      const d = Math.max(...zs) - Math.min(...zs) + 3.2 * (new Set(xs).size <= 2 ? 1.5 : 1)
      const dist = fit(w, d) + 0.6
      const stacked = new Set(xs).size <= 2          // phone: two columns, so look down on them to keep the rows apart
      const el = stacked ? 1.0 : 0.42
      const cz = (Math.max(...zs) + Math.min(...zs)) / 2
      want.look.set(0, 0.5, cz)
      want.pos.set(0, Math.sin(el) * dist + 0.3, cz + Math.cos(el) * dist)
    } else {
      const i = GROUPS.findIndex((g) => g.id === state.group)
      const p = places[i] ?? { x: 0, z: 0 }
      const narrow = aspect < 0.9                       // portrait phone: the cards are what matters, so come in closer
      const dist = fit(TRAY.w + (narrow ? 0.7 : 2.6), narrow ? 3.4 : 4.6) + 0.9
      const enter = state.mode === 'enter'
      const el = 0.5
      want.look.set(p.x, enter ? 1.5 : 1.25, p.z)
      want.pos.set(p.x, Math.sin(el) * dist + 0.5, p.z + Math.cos(el) * dist * (enter ? 0.62 : 1))
    }
    const k = calm ? 80 : state.mode === 'enter' ? 5 : 2.8
    if (!cur.current) cur.current = { pos: want.pos.clone(), look: want.look.clone() }
    const c = cur.current
    c.pos.x = damp(c.pos.x, want.pos.x, k, dt); c.pos.y = damp(c.pos.y, want.pos.y, k, dt); c.pos.z = damp(c.pos.z, want.pos.z, k, dt)
    c.look.x = damp(c.look.x, want.look.x, k, dt); c.look.y = damp(c.look.y, want.look.y, k, dt); c.look.z = damp(c.look.z, want.look.z, k, dt)
    camera.position.copy(c.pos)
    camera.lookAt(c.look)
    camera.updateMatrixWorld(true)
  })
  return null
}

function Frames({ onReady }: { onReady: () => void }) {
  const n = useRef(0)
  useFrame(() => { if (n.current < 3 && ++n.current === 3) onReady() })
  return null
}

export interface HubSceneProps extends Common {
  active: boolean
  small: boolean
  onReady: () => void
  /** Calm mode draws on demand: true for a moment after anything changed, so the canvas can paint the new pose. */
  burst: boolean
}

export default function HubScene({ state, ui, hits, calm, active, small, onReady, burst }: HubSceneProps) {
  const fonts = useFontsReady()
  const places = useMemo(() => boxPlaces(GROUPS.length, small ? 2 : GROUPS.length), [small])
  return (
    <Canvas frameloop={calm ? (burst ? 'always' : 'demand') : active ? 'always' : 'never'} dpr={[1, small ? 1 : 1.75]}
      camera={{ fov: 34, near: 0.1, far: 80, position: [0, 4, 20] }}
      gl={{ antialias: !small, alpha: true, powerPreference: 'default' }} onCreated={({ gl }) => gl.setClearColor(0x000000, 0)}>
      <fog attach="fog" args={['#000', 22, 48]} />
      <ambientLight intensity={0.5} />
      <directionalLight position={[5, 9, 7]} intensity={1.1} color="#ffe6b0" />
      <pointLight position={[0, 4, -9]} intensity={8} distance={30} color={GOLD} />
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.001, -4]}>
        <planeGeometry args={[90, 60]} />
        <meshStandardMaterial color="#050505" metalness={0.5} roughness={0.55} />
      </mesh>
      <Dust n={small ? 30 : 70} calm={calm} />
      {GROUPS.map((g, i) => (
        <Box key={g.id} group={g.id} placeAt={places[i]} state={state} ui={ui} hits={hits} calm={calm} fonts={fonts} />
      ))}
      <Rig state={state} places={places} calm={calm} />
      <Frames onReady={onReady} />
    </Canvas>
  )
}
