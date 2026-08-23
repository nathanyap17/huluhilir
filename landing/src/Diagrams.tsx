/// Diagrams that show the mechanism, not decoration.
///
/// Each one draws the thing the adjacent prose describes: water actually runs
/// downhill across the slope, the four signals actually converge on one
/// output, the five layers actually stack. They are inline SVG with CSS/anime
/// driving them, so they stay crisp at any size and theme with the page.
import { useEffect, useRef } from 'react';
import { animate, stagger } from 'animejs';

/// The product thesis in one figure: an infection upslope becomes a scheduled
/// arrival below. The droplet path is the same curve the terrain follows, so
/// the animation is showing transport, not just moving a dot around.
export function SlopeDiagram() {
  const root = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const el = root.current;
    if (!el) return;

    const hide = (sel: string) =>
      el.querySelectorAll<SVGElement>(sel).forEach((n) => (n.style.opacity = '0'));

    const revealAll = () =>
      el.querySelectorAll<SVGElement>('.terrace, .vine, .sig, .wire, .verdict-node')
        .forEach((n) => (n.style.opacity = ''));

    hide('.terrace, .vine');
    // Backstop: whatever happens to the animation, the figure is readable.
    const failsafe = window.setTimeout(revealAll, 4000);

    const observer = new IntersectionObserver(
      (entries) => {
        if (!entries[0].isIntersecting) return;
        observer.disconnect();

        animate(el.querySelectorAll('.terrace'), {
          opacity: [0, 1],
          translateY: [14, 0],
          duration: 700,
          delay: stagger(90),
          ease: 'out(3)',
        });
        animate(el.querySelectorAll('.vine'), {
          opacity: [0, 1],
          scale: [0.5, 1],
          duration: 500,
          delay: stagger(120, { start: 400 }),
          ease: 'out(4)',
        });
        // The droplet runs the slope on a loop — the disease arriving, over
        // and over, which is what a rain pulse actually does.
        animate(el.querySelectorAll('.flow-drop'), {
          offsetDistance: ['0%', '100%'],
          opacity: [{ to: 1, duration: 200 }, { to: 0, duration: 300, delay: 1400 }],
          duration: 2200,
          delay: stagger(700),
          loop: true,
          ease: 'inOut(2)',
        });
      },
      { threshold: 0.3 },
    );
    observer.observe(el);
    return () => {
      window.clearTimeout(failsafe);
      observer.disconnect();
    };
  }, []);

  return (
    <svg ref={root} className="fig" viewBox="0 0 720 300" role="img"
         aria-label="Water and disease moving downhill across terraced pepper blocks">
      <defs>
        <linearGradient id="slopeFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#6f9354" />
          <stop offset="100%" stopColor="#3e5233" />
        </linearGradient>
      </defs>

      {[0, 1, 2, 3].map((i) => (
        <path
          key={i}
          className="terrace"
          d={`M ${40 + i * 30} ${90 + i * 48} H ${690 - i * 20} v 30 H ${40 + i * 30} Z`}
          fill="url(#slopeFill)"
          opacity={1 - i * 0.13}
        />
      ))}

      {/* The path the droplets follow is declared once and reused, so the
          motion cannot drift from the terrain drawn underneath it. */}
      <path id="flowPath" d="M 80 100 C 240 130, 300 190, 420 220 S 600 265, 660 275"
            fill="none" stroke="#8a8a70" strokeWidth="2" strokeDasharray="5 7" opacity="0.65" />

      {[0, 1, 2].map((i) => (
        <circle key={i} className="flow-drop" r="6" fill="#cc7a5c" opacity="0.9"
                style={{ offsetPath: "path('M 80 100 C 240 130, 300 190, 420 220 S 600 265, 660 275')" }} />
      ))}

      {[
        { x: 80, y: 100, label: 'Hulu', state: '#cc7a5c' },
        { x: 300, y: 175, label: '', state: '#ebc366' },
        { x: 480, y: 228, label: '', state: '#5a5a40' },
        { x: 660, y: 275, label: 'Hilir', state: '#5a5a40' },
      ].map((n, i) => (
        <g key={i} className="vine">
          <circle cx={n.x} cy={n.y} r="11" fill={n.state} stroke="#fff" strokeWidth="2.5" />
          {n.label && (
            <text x={n.x} y={n.y - 20} textAnchor="middle"
                  fill="#5a5a40" fontSize="13" fontWeight="600">{n.label}</text>
          )}
        </g>
      ))}
    </svg>
  );
}

/// Four inputs, one output. Drawn as convergence because that is literally
/// what the root agent does — the alternative (a list of four bullets) shows
/// the inputs but hides the only interesting part.
export function ArbitrationDiagram() {
  const root = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const el = root.current;
    if (!el) return;

    const hide = (sel: string) =>
      el.querySelectorAll<SVGElement>(sel).forEach((n) => (n.style.opacity = '0'));

    const revealAll = () => {
      el.querySelectorAll<SVGElement>('.sig, .verdict-node').forEach((n) => (n.style.opacity = ''));
      el.querySelectorAll<SVGPathElement>('.wire').forEach((n) => (n.style.strokeDashoffset = '0'));
    };

    hide('.sig, .verdict-node');
    const failsafe = window.setTimeout(revealAll, 4000);

    const observer = new IntersectionObserver(
      (entries) => {
        if (!entries[0].isIntersecting) return;
        observer.disconnect();

        animate(el.querySelectorAll('.sig'), {
          opacity: [0, 1],
          translateX: [-24, 0],
          duration: 600,
          delay: stagger(130),
          ease: 'out(3)',
        });
        // Lines draw themselves toward the arbitrator, then the verdict lands.
        animate(el.querySelectorAll('.wire'), {
          strokeDashoffset: [220, 0],
          duration: 900,
          delay: stagger(130, { start: 300 }),
          ease: 'inOut(2)',
        });
        animate(el.querySelectorAll('.verdict-node'), {
          opacity: [0, 1],
          scale: [0.7, 1],
          duration: 700,
          delay: 1100,
          ease: 'out(4)',
        });
      },
      { threshold: 0.35 },
    );
    observer.observe(el);
    return () => {
      window.clearTimeout(failsafe);
      observer.disconnect();
    };
  }, []);

  const signals = [
    { y: 40, colour: '#cc7a5c', text: 'Lesi pangkal dikesan' },
    { y: 100, colour: '#5a5a40', text: 'Racun perlu 24 j kering' },
    { y: 160, colour: '#6c86a8', text: '46 mm hujan esok' },
    { y: 220, colour: '#ebc366', text: 'Blok hilir ~4 hari' },
  ];

  return (
    <svg ref={root} className="fig" viewBox="0 0 720 270" role="img"
         aria-label="Four conflicting signals resolved into one sequenced action">
      {signals.map((s, i) => (
        <path key={`w${i}`} className="wire"
              d={`M 250 ${s.y + 10} C 340 ${s.y + 10}, 360 135, 440 135`}
              fill="none" stroke={s.colour} strokeWidth="2.5" opacity="0.75"
              strokeDasharray="220" strokeDashoffset="0" />
      ))}

      {signals.map((s, i) => (
        <g key={i} className="sig">
          <rect x="10" y={s.y} width="240" height="22" rx="11" fill="#fff" stroke="#e4dfd5" />
          <circle cx="26" cy={s.y + 11} r="4.5" fill={s.colour} />
          <text x="40" y={s.y + 15} fill="#2d2d2d" fontSize="11.5">{s.text}</text>
        </g>
      ))}

      <g className="verdict-node">
        <rect x="440" y="100" width="265" height="70" rx="16" fill="#5a5a40" />
        <text x="458" y="126" fill="rgba(255,255,255,0.7)" fontSize="10" letterSpacing="1.4">
          SATU TINDAKAN
        </text>
        <text x="458" y="150" fill="#fff" fontSize="14.5" fontWeight="600">
          Parit hari ini · sembur Khamis
        </text>
      </g>
    </svg>
  );
}
