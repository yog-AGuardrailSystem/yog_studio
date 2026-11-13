# Motion inventory

Every animated behaviour is tagged `data-motion="<family>:<name>[:<n>]"` in the DOM. `e2e/motion.mjs` visits the landing
page, How it works and the workbench, collects the distinct ids it sees, and fails if there are fewer than 300.

**Counting rules (be honest when quoting this).** One id = one animated element. Some families are data-driven, so the
count grows with the program on screen (one id per token, per AST node, per test row). The number below is therefore
"distinct animated elements in the tour", not "distinct kinds of animation". The kinds are the families in the table.

| | before this round | after |
|---|---|---|
| distinct animated elements in the tour | ~30 (hand count: 35 `motion.*` elements, 9 keyframe sets, 8 scroll triggers, 1 WebGL scene) | 451 measured on 2026-11-08 (299 on the landing page alone) |
| kinds (families) of behaviour | ~12 | 40+ (table) |

## Controls and fallbacks (apply to everything)
- **Pause / resume**: header button on every page (`motion-toggle`). Sets `html[data-motion=paused]`; CSS animation and
  transitions stop, Motion (framer) runs with `reducedMotion="always"`, canvas/rAF effects do not start. Remembered in
  localStorage.
- **OS "reduce motion"**: same effect, automatically. Content that animates in is shown in its final state.
- **WebGL**: at most two live contexts on a page: the hero globe (stops drawing off-screen or in a hidden tab) and the decision gate (mounted only when its section is near the viewport); everything else is DOM, SVG, CSS or one 2D canvas.
- Off-screen work stops: the particle field pauses with an IntersectionObserver; scenes start when scrolled into view.

## Families

| family | what moves | trigger | calm fallback | test |
|---|---|---|---|---|
| `scene:lexer:*` | real tokens pop in line by line; line highlight sweeps | in view, Replay | final state shown | e2e/motion.mjs |
| `scene:parser:*` | AST rows slide into place, indented by depth | in view, Replay | final state | e2e/motion.mjs |
| `scene:semantic:*` | symbol table rows appear, ticks spring in | in view, Replay | final state | e2e/motion.mjs |
| `scene:eval:*` | proof trace steps in order, verdict stamps | in view, Replay | final state | e2e/motion.mjs |
| `pipe:node/pulse/link/label` | conveyor: each stage lights as the packet arrives; links fill | in view | stopped, all lit | e2e/landing.mjs |
| `pipe:packet`, `pipe:packet-trail` | packet crosses the diagram | in view | stopped | e2e/motion.mjs |
| `card:<group>:*` | per-example flow: dots travel, beam to ALLOW/DENY (drawn from the program's real counts) | always | beam not rendered, dots stopped | e2e/motion.mjs |
| `hero:globe` | ~14,000 gold dots in an orb (rim light, faint far side, sparse halo shell) with a letter-shaped YOG core of ~9,000 dots through its depth: swings side-on to front-on on landing, turns slowly, drag with inertia, hover dents the skin and nudges the 96 dots nearest the pointer by a few pixels (only while it is over the orb), click sends a ripple and a debris burst | page load, pointer | one still frame facing the viewer; static gold wordmark without WebGL | e2e/hero.mjs |
| `hub:stage` | /studio: five 3D boxes (gold edge lines, floating dust). Hover cracks a lid; click flies the camera to the box, the lid swings open and its tool cards rise; hovering a card lifts it and tints it with its own accent; clicking one flies it toward you, then opens the tool. The YOG monogram opens an About panel (halftone logo, scrambled text builds in) while the scene slides aside | pointer, keyboard, tap | no camera flight and no scramble: every change is instant; plain tiles without WebGL | e2e/hub.mjs |
| `fx:scroll-rail` | progress bar from scroll position | scroll | static | e2e/motion.mjs |
| `fx:dot:*` | section dots glow for the current section | scroll | static | e2e/motion.mjs |
| `fx:particles` | constellation canvas | page load | not started | e2e/motion.mjs |
| `fx:cursor-glow` | light follows the pointer | pointer (fine pointers only) | not rendered | manual |
| `fx:click-ripple` | ring from every click | click | not created | e2e/motion.mjs |
| `fx:scramble:*` | eyebrow text scrambles into place | first view | plain text | e2e/motion.mjs |
| `fx:magnetic:*` | CTA leans toward the pointer | hover | none | manual |
| `fx:parallax:*` | hero title drifts | scroll | none | manual |
| `fx:kw:*` | keyword marquee, opposite direction | always | stopped | e2e/motion.mjs |
| `wb:token:*` | tokens stream in as you type | edit | final state | e2e/motion.mjs |
| `wb:ast:*`, `wb:ast-leaf:*` | AST nodes rise in by depth | tab open | final | e2e/motion.mjs |
| `wb:test:*` | result rows flip when their decision changes | run | final | e2e/motion.mjs |
| `wb:diagnostic:*` | error cards shake once | error appears | none | e2e/motion.mjs |
| `wb:compiles-badge`, `wb:draft-card`, `wb:toast`, `wb:palette`, `wb:tour` | pop-in | open | none | e2e/motion.mjs |
| `wb:tabline` | tab underline slides between tabs (shared layout) | tab change | jumps | e2e/motion.mjs |
| `wb:compile-ring` | ring spins while the compiler runs | edit | spins slowly (spinner exempt from pause) | e2e/workbench.mjs |
| `wb:ret:*` | similarity bars grow to their score | retrieval | final | e2e/motion.mjs |
| `wb:attempt:*` | draft attempt log lines rise in | draft | final | e2e/motion.mjs |
| all-green burst | particles when every test passes | run | not rendered under OS reduce | e2e/workbench.mjs |

CSS-only micro-interactions not individually tagged: button shine sweep, link underline grow, chip pop, card lift and
spotlight, pipeline node hover lift, marquee hover pause. They stop with the pause control and under reduced motion.

## What cannot be verified here
Smoothness on a real GPU. The tour runs in headless Chrome with a software renderer; frame rate there says nothing about
user hardware. Eyeball the landing page and the decision gate on a real machine before the demo.
