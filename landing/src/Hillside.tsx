import { useEffect, useRef } from 'react';
import { createTimeline, svg, type Timeline } from 'animejs';
import { STATE } from './content';

/// The hero: one pepper hillside, one rain pulse, one decision.
///
/// It plays the product's core moment in order -- a lesion on the top block
/// (hulu), the runoff carrying it downhill toward the river (hilir), the blocks
/// below turning Alerted, and the agent's single instruction -- so the premise
/// is seen before it is read. Blocks 4 and 5 stay Protected on purpose: the
/// projection weakens with distance, and the page should not imply that
/// everything downhill is lost.

type Pt = [number, number];
type Block = { at: Pt; tag: string; end: keyof typeof STATE };

const W = 1200;
const H = 640;

const BLOCKS: Block[] = [
  { at: [1070, 236], tag: 'Collar lesion · 91%', end: 'harmed' },
  { at: [960, 292], tag: '~2 days · estimate', end: 'alerted' },
  { at: [850, 348], tag: '~4 days · estimate', end: 'alerted' },
  { at: [740, 402], tag: 'Low risk · estimate', end: 'protected' },
  // The last block has no tag: it would crowd the headline on narrow screens,
  // and Block 4 already makes the point that risk fades with distance.
  { at: [630, 452], tag: '', end: 'protected' },
];

const SURFACE_PTS: Pt[] = [[-20, 622], [200, 604], [430, 540], ...BLOCKS.map((b) => b.at).reverse(), [1220, 196]];
const RUNOFF_PTS: Pt[] = [...BLOCKS.map((b) => [b.at[0], b.at[1] + 2] as Pt), [430, 542], [260, 596], [150, 612]];

/// Catmull-Rom through the points, as cubic Béziers: a smooth hillside that
/// passes exactly through every block.
function smooth(pts: Pt[]): string {
  let d = `M${pts[0][0]},${pts[0][1]}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[i - 1] ?? pts[i];
    const p1 = pts[i];
    const p2 = pts[i + 1];
    const p3 = pts[i + 2] ?? p2;
    const c1 = [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6];
    const c2 = [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6];
    d += ` C${c1[0].toFixed(1)},${c1[1].toFixed(1)} ${c2[0].toFixed(1)},${c2[1].toFixed(1)} ${p2[0]},${p2[1]}`;
  }
  return d;
}

const SURFACE = smooth(SURFACE_PTS);
const RUNOFF = smooth(RUNOFF_PTS);

// How far along the runoff each block sits (chord lengths; close enough to
// time each block's reaction to the moment the water reaches it).
const REACH = (() => {
  const seg = RUNOFF_PTS.slice(1).map((p, i) => Math.hypot(p[0] - RUNOFF_PTS[i][0], p[1] - RUNOFF_PTS[i][1]));
  const total = seg.reduce((a, b) => a + b, 0);
  let run = 0;
  return [0, ...seg.map((s) => (run += s) / total)];
})();

// Fixed pseudo-random rain, so every loop looks the same.
const RAIN = Array.from({ length: 70 }, (_, i) => ({
  x: (i * 173) % (W + 60),
  y: -((i * 97) % 200),
  delay: ((i * 37) % 90) / 100,
  len: 16 + ((i * 13) % 14),
}));

export default function Hillside() {
  const root = useRef<SVGSVGElement>(null);
  const card = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = root.current;
    if (!el) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      el.classList.add('is-still'); // final frame, drawn by CSS
      card.current?.classList.add('is-shown');
      return;
    }

    const P = STATE.protected.colour;
    const q = (s: string) => el.querySelectorAll<SVGElement>(s);
    const runoff = svg.createDrawable(q('.runoff'));
    const FLOW_AT = 1900;
    const FLOW_MS = 4200;

    const tl: Timeline = createTimeline({ loop: true, defaults: { ease: 'out(3)' } });
    tl.add(q('.rain'), { opacity: [0, 1], duration: 600 }, 0)
      .add(q('.b0 .vine'), { fill: [P, STATE.harmed.colour], duration: 500 }, 1100)
      .add(q('.b0 .collar'), { stroke: [P, STATE.harmed.colour], duration: 500 }, 1100)
      .add(q('.b0 .ping'), { scale: [0.6, 2.8], opacity: [0.9, 0], duration: 1300, ease: 'out(2)' }, 1100)
      .add(q('.b0 .tag'), { opacity: [0, 1], translateY: [6, 0], duration: 500 }, 1300)
      .add(runoff, { draw: ['0 0', '0 1'], duration: FLOW_MS, ease: 'inOut(1.6)' }, FLOW_AT)
      .add(q('.river'), { opacity: [0.35, 1], duration: 900 }, FLOW_AT + FLOW_MS - 600);

    BLOCKS.slice(1).forEach((b, i) => {
      const at = FLOW_AT + REACH[i + 1] * FLOW_MS - 200;
      const to = STATE[b.end].colour;
      tl.add(q(`.b${i + 1} .vine`), { fill: [P, to], duration: 450 }, at)
        .add(q(`.b${i + 1} .collar`), { stroke: [P, to], duration: 450 }, at)
        .add(q(`.b${i + 1} .tag`), { opacity: [0, 1], translateY: [6, 0], duration: 450 }, at + 120);
      if (b.end !== 'protected') {
        tl.add(q(`.b${i + 1} .ping`), { scale: [0.6, 2.3], opacity: [0.8, 0], duration: 1100 }, at);
      }
    });

    tl.add(q('.rain'), { opacity: [1, 0], duration: 900 }, 5200)
      .call(() => card.current?.classList.add('is-shown'), 6300)
      // Hold on the decision, then let the water drain away and start again.
      .call(() => card.current?.classList.remove('is-shown'), 11800)
      .add(q('.tag'), { opacity: [1, 0], duration: 500 }, 11900)
      .add(runoff, { draw: ['0 1', '1 1'], duration: 1400, ease: 'in(2)' }, 11900)
      .add(q('.river'), { opacity: [1, 0.35], duration: 900 }, 12600)
      .add(q('.vine'), { fill: P, duration: 700 }, 12200)
      .add(q('.collar'), { stroke: P, duration: 700 }, 12200)
      .add(q('.rain'), { opacity: 0, duration: 1 }, 13600);

    // Background tabs throttle animation frames; pause rather than let the
    // loop drift, and pick up where it was when the tab returns.
    const onVis = () => (document.hidden ? tl.pause() : tl.play());
    document.addEventListener('visibilitychange', onVis);
    return () => {
      document.removeEventListener('visibilitychange', onVis);
      tl.revert();
    };
  }, []);

  return (
    <figure className="hillside" aria-labelledby="hillside-cap">
      <svg ref={root} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMaxYMax slice" role="img"
        aria-label="A pepper farm on a slope. Rain falls, a lesion appears on the top block, and runoff carries it down past the next two blocks, which turn amber, toward the river.">
        <defs>
          <linearGradient id="ground" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#274A33" />
            <stop offset="1" stopColor="#10211A" />
          </linearGradient>
          <linearGradient id="riverfill" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stopColor="#7FF0FF" stopOpacity="0.9" />
            <stop offset="1" stopColor="#28C4EE" stopOpacity="0" />
          </linearGradient>
          <filter id="glow" x="-10%" y="-30%" width="120%" height="160%">
            <feGaussianBlur stdDeviation="6" result="b" />
            <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>

        <g className="rain" opacity="0">
          {RAIN.map((r, i) => (
            <line key={i} x1={r.x} y1={r.y} x2={r.x - 5} y2={r.y + r.len}
              style={{ animationDelay: `${r.delay}s` }} />
          ))}
        </g>

        <path d={`${SURFACE} L1220,${H + 10} L-20,${H + 10} Z`} fill="url(#ground)" />
        {/* Soil strata: the surface repeated below itself, fading out. */}
        {[20, 44, 74, 110, 152].map((dy, i) => (
          <path key={dy} d={SURFACE} transform={`translate(0 ${dy})`} className="stratum"
            style={{ opacity: 0.2 - i * 0.032 }} />
        ))}
        <path d={SURFACE} className="surface" />

        <path className="river" d="M-20,626 C80,612 180,614 300,622 C200,634 80,640 -20,640 Z" fill="url(#riverfill)" opacity="0.35" filter="url(#glow)" />
        <path d={RUNOFF} className="runoff" filter="url(#glow)" />

        {BLOCKS.map((b, i) => (
          <g key={i} className={`block b${i} end-${b.end}`} transform={`translate(${b.at[0]} ${b.at[1]})`}>
            <ellipse className="pad" cx="0" cy="2" rx="36" ry="7" />
            <circle className="ping" cx="0" cy="-2" r="15" />
            <line className="post" x1="0" y1="0" x2="0" y2="-66" />
            {/* The vine: a peppercorn cluster up the post, coloured by state. */}
            {[[-7, -58, 6.5], [7, -50, 7], [-7, -41, 7.5], [7, -32, 7], [-6, -22, 6.5], [5, -13, 5.5]].map(([cx, cy, r], k) => (
              <circle key={k} className="vine" cx={cx} cy={cy} r={r} fill={STATE.protected.colour} />
            ))}
            <circle className="collar" cx="0" cy="-2" r="10" stroke={STATE.protected.colour} />
            <text className="name" x="0" y="-80">Block {i + 1}</text>
            {b.tag && <text className="tag" x="0" y="32" opacity="0">{b.tag}</text>}
          </g>
        ))}

        <text className="pulse-label" x={W - 24} y="44">Rain pulse: ~46 mm tomorrow (estimate)</text>
      </svg>

      <div ref={card} className="decision">
        <span className="decision-by">Router agent</span>
        <p>Clear the drain today. Drench Thursday morning.</p>
        <span className="decision-why">The drench needs 24 dry hours (rules table). Thursday is the first.</span>
      </div>

      <figcaption id="hillside-cap" className="legend">
        {Object.values(STATE).map((s) => (
          <span key={s.label}><i style={{ background: s.colour }} />{s.label}</span>
        ))}
      </figcaption>
    </figure>
  );
}
