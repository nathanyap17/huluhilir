import { useEffect, useRef } from 'react';
import { animate, stagger, createScope, type Scope } from 'animejs';
import { SlopeDiagram, ArbitrationDiagram } from './Diagrams';
import {
  APP_URL,
  REPO_URL,
  API_DOCS_URL,
  LAYERS,
  SIGNALS,
  STATS,
  RULES,
} from './content';

export default function App() {
  const root = useRef<HTMLDivElement>(null);
  const scope = useRef<Scope | null>(null);

  useEffect(() => {
    scope.current = createScope({ root: root as React.RefObject<HTMLElement> }).add(() => {
      // Respect the OS setting rather than animating regardless: this page is
      // read by people on phones in the field, and motion is not free.
      const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      if (still) return; // nothing was hidden; leave the page as authored

      // Only now hide the reveal targets, so everything above this line is a
      // no-op path that leaves content visible.
      document.body.classList.add('motion-ready');

      // Backstop: whatever happens to the animations, the page is fully
      // readable shortly after load. Background tabs throttle
      // requestAnimationFrame heavily, and a half-finished fade is a blank
      // page to anyone who lands on it from a preview or a link opened in
      // the background.
      const failsafe = window.setTimeout(() => {
        document.body.classList.remove('motion-ready');
        document.querySelectorAll<HTMLElement>('.js-reveal').forEach((el) => {
          el.style.opacity = '1';
        });
      }, 4000);

      animate('.hero-reveal', {
        opacity: [0, 1],
        translateY: [22, 0],
        duration: 780,
        delay: stagger(95),
        ease: 'out(3)',
      });

      // The slope bands settle downhill in sequence — the product's whole
      // premise (water, and disease, moving hulu → hilir) stated visually
      // before a word of it is read.
      animate('.slope-band', {
        scaleX: [0.35, 1],
        opacity: [0, 1],
        duration: 1000,
        delay: stagger(110, { start: 260 }),
        ease: 'out(4)',
      });

      // A droplet running down the slope, looping. Deliberately slow: it is
      // ambient, not something demanding attention.
      animate('.drop', {
        translateY: [0, 168],
        translateX: [0, 116],
        opacity: [{ to: 1, duration: 240 }, { to: 0, duration: 420, delay: 900 }],
        duration: 1900,
        delay: stagger(620),
        loop: true,
        ease: 'inOut(2)',
      });

      // Parallax on the hero figure only. A rAF-throttled scroll handler
      // rather than a library: one transform on one element is not worth a
      // dependency, and anything heavier would cost more on a low-spec phone
      // than the effect is worth.
      let ticking = false;
      const onScroll = () => {
        if (ticking) return;
        ticking = true;
        requestAnimationFrame(() => {
          const y = window.scrollY;
          document.querySelectorAll<HTMLElement>('[data-parallax]').forEach((el) => {
            const rate = Number(el.dataset.parallax ?? '0.2');
            el.style.transform = `translate3d(0, ${(y * rate).toFixed(1)}px, 0)`;
          });
          ticking = false;
        });
      };
      window.addEventListener('scroll', onScroll, { passive: true });

      // Scroll reveals. IntersectionObserver rather than a scroll handler so
      // this stays cheap on a low-spec phone.
      const observer = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (!entry.isIntersecting) return;
            animate(entry.target, {
              opacity: [0, 1],
              translateY: [26, 0],
              duration: 700,
              ease: 'out(3)',
            });
            observer.unobserve(entry.target);
          });
        },
        { threshold: 0.16 },
      );
      document
        .querySelectorAll('.js-reveal:not(.hero-reveal)')
        .forEach((el) => observer.observe(el));

      // Count the headline figures up, so the numbers register as findings
      // rather than decoration.
      document.querySelectorAll<HTMLElement>('.stat-num').forEach((el) => {
        const target = Number(el.dataset.value ?? '0');
        const suffix = el.dataset.suffix ?? '';
        const counter = { v: 0 };
        const seen = new IntersectionObserver((entries) => {
          if (!entries[0].isIntersecting) return;
          seen.disconnect();
          animate(counter, {
            v: target,
            duration: 1500,
            ease: 'out(3)',
            onUpdate: () => {
              el.textContent = Math.round(counter.v).toLocaleString() + suffix;
            },
          });
        });
        seen.observe(el);
      });

      return () => {
        window.clearTimeout(failsafe);
        window.removeEventListener('scroll', onScroll);
        observer.disconnect();
      };
    });

    return () => scope.current?.revert();
  }, []);

  return (
    <div ref={root}>
      <header className="site-header">
        <div className="wrap">
          <a className="brand" href="#top">
            <span className="brand-name">HuluHilir</span>
            <img className="brand-logo" src="brand/logo.png" alt="" />
          </a>
          <div className="header-spacer" />
          <nav className="header-links">
            <a className="btn btn-ghost" href={REPO_URL} target="_blank" rel="noreferrer">
              Repositori
            </a>
            <a className="btn btn-primary" href={APP_URL}>
              Buka Aplikasi
            </a>
          </nav>
        </div>
      </header>

      <main id="top">
        <section className="hero">
          <div className="wrap">
            <p className="eyebrow hero-reveal js-reveal">
              AICC 2026 · Track 3, Category B · Finalist
            </p>
            <h1 className="hero-reveal js-reveal">
              The disease travels <span className="accent">downhill</span>.
              <br />
              So does the warning.
            </h1>
            <p className="hero-tag hero-reveal js-reveal">
              Dari hulu ke hilir — sebelum penyakit sampai.
            </p>
            <p className="hero-lede hero-reveal js-reveal">
              Phytophthora foot rot does not spread evenly. It moves downhill through water, in
              rain pulses. HuluHilir models a farm as a directed elevation graph, then arbitrates
              between diagnosis, weather, treatment rules and spread projection to give a
              smallholder <strong>one action, one time, one reason</strong>.
            </p>
            <div className="hero-cta hero-reveal js-reveal">
              <a className="btn btn-primary" href={APP_URL}>
                Buka Aplikasi →
              </a>
              <a className="btn btn-ghost" href={REPO_URL} target="_blank" rel="noreferrer">
                Lihat Kod
              </a>
              <a className="btn btn-ghost" href={API_DOCS_URL} target="_blank" rel="noreferrer">
                API Docs
              </a>
            </div>
            <p className="hero-meta hero-reveal js-reveal">
              Live on Cloud Run + Vertex AI. Open the app and tap “Lihat ladang demo”.
            </p>

            <div className="slope-figure" aria-hidden="true" data-parallax="0.16">
              {[0, 1, 2, 3, 4].map((i) => (
                <div
                  key={i}
                  className="slope-band"
                  style={{
                    top: i * 38,
                    height: 26,
                    marginLeft: i * 34,
                    marginRight: (4 - i) * 12,
                    background: `hsl(${86 - i * 4} ${26 - i * 3}% ${34 + i * 9}%)`,
                  }}
                />
              ))}
              {[0, 1, 2].map((i) => (
                <div key={`d${i}`} className="drop" style={{ top: 8, left: 60 + i * 22 }} />
              ))}
            </div>
          </div>
        </section>

        <section className="alt">
          <div className="wrap">
            <div className="section-head js-reveal">
              <p className="eyebrow">The problem</p>
              <h2>A catchment-scale disease, fought with single-plant tools.</h2>
              <p>
                Sarawak grows over 98% of Malaysia’s pepper, on deliberately steep slopes — because
                pepper vines rot in waterlogged soil. That same drainage becomes the pathogen’s
                highway. An infection upslope is a scheduled arrival below.
              </p>
            </div>
            <div className="js-reveal" style={{ marginBottom: 34 }}>
              <SlopeDiagram />
            </div>
            <div className="stats">
              {STATS.map((s) => (
                <div className="stat js-reveal" key={s.label}>
                  <div className="stat-num" data-value={s.value} data-suffix={s.suffix}>
                    0
                  </div>
                  <div className="stat-label">{s.label}</div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section>
          <div className="wrap">
            <div className="section-head js-reveal">
              <p className="eyebrow">The core moment</p>
              <h2>Four signals that contradict each other.</h2>
              <p>
                Naïvely, these are four conflicting instructions. Spraying today would wash the
                treatment off before it binds. The agent holds all four at once and sequences them.
              </p>
            </div>
            <div className="js-reveal" style={{ marginBottom: 30 }}>
              <ArbitrationDiagram />
            </div>
            <div className="arb">
              <div>
                {SIGNALS.map((sig) => (
                  <div className="signal js-reveal" key={sig.source}>
                    <span className="signal-dot" style={{ background: sig.colour }} />
                    <div>
                      <div className="signal-src">{sig.source}</div>
                      <div className="signal-txt">{sig.text}</div>
                    </div>
                  </div>
                ))}
              </div>
              <div className="verdict js-reveal">
                <p className="eyebrow">Arbitrated output</p>
                <p className="verdict-line">“Clear the drain today. Spray Thursday morning.”</p>
                <p className="verdict-why">
                  The spray is deferred, not cancelled — and the deferral is reconciled
                  deterministically against the actual spray-window tool call, not left to the
                  model’s account of itself.
                </p>
              </div>
            </div>
          </div>
        </section>

        <section className="alt">
          <div className="wrap">
            <div className="section-head js-reveal">
              <p className="eyebrow">Architecture</p>
              <h2>Five layers, one instruction.</h2>
            </div>
            <div className="layers">
              {LAYERS.map((l) => (
                <div className="layer js-reveal" key={l.id}>
                  <div className="layer-id">{l.id}</div>
                  <div>
                    <h3>{l.title}</h3>
                    <p>{l.body}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section>
          <div className="wrap">
            <div className="section-head js-reveal">
              <p className="eyebrow">Non-negotiable</p>
              <h2>Commitments held even where a shortcut was faster.</h2>
              <p>
                These come from the submitted proposal. Several of them cost real engineering time
                to keep.
              </p>
            </div>
            <div className="rules">
              {RULES.map((r) => (
                <div className="rule js-reveal" key={r.title}>
                  <strong>{r.title}</strong>
                  {r.body}
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="cta-band alt">
          <div className="wrap js-reveal">
            <h2>See it running.</h2>
            <p>
              The demo farm is seeded and live. Open the app and tap “Lihat ladang demo” — no
              registration, no walking a hillside required.
            </p>
            <div className="cta-row">
              <a className="btn btn-terra" href={APP_URL}>
                Buka Aplikasi →
              </a>
              <a className="btn btn-ghost" href={REPO_URL} target="_blank" rel="noreferrer">
                Repositori
              </a>
            </div>
          </div>
        </section>
      </main>

      <footer>
        <div className="wrap footer-row">
          <div>
            <strong>HuluHilir</strong> — Team SMILING FACE WITH SUNGLASSES
            <br />
            Nathan Yap Jia De · Zoe Tan An Xuen · Abraham Pang Exin
          </div>
          <div>
            <a href={REPO_URL} target="_blank" rel="noreferrer">
              GitHub
            </a>{' '}
            ·{' '}
            <a href={API_DOCS_URL} target="_blank" rel="noreferrer">
              API
            </a>{' '}
            ·{' '}
            <a href={APP_URL}>Aplikasi</a>
            <br />
            Competition submission. Not for production agricultural decisions.
          </div>
        </div>
      </footer>
    </div>
  );
}
