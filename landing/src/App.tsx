import { useEffect, useRef, useState } from 'react';
import QRCode from 'qrcode';
import Hillside from './Hillside';
import {
  APK_PATH, APK_URL, REPO_URL, API_DOCS_URL, DEMO_VIDEO_URL,
  FAILURES, EVIDENCE, GUARDS, LAYERS, ROUTER, SUBAGENTS, TOOLS, CALENDAR,
  TRIAGE_BLOCKS, COUNCIL_VOICES, COUNCIL_RANKING, FLOW, FEED, type AgentNode,
} from './content';

export default function App() {
  return (
    <>
      <Nav />
      <main>
        <Hero />
        <Problem />
        <Method />
        <Agents />
        <Council />
        <Flow />
        <GetApp />
      </main>
      <Footer />
    </>
  );
}

function Nav() {
  return (
    <header className="nav">
      <div className="wrap nav-inner">
        <a href="#top" className="nav-logo" aria-label="PepperDex Sarawak, back to top">
          <img src="brand/logo.png" alt="PepperDex Sarawak" width="152" height="64" />
        </a>
        <nav aria-label="Sections">
          <a href="#method">How it decides</a>
          <a href="#agents">Agents</a>
          <a href="#council">Council</a>
          <a href="#get" className="nav-cta">Get the app</a>
        </nav>
      </div>
    </header>
  );
}

function Hero() {
  return (
    <section className="hero" id="top">
      <Hillside />
      <div className="wrap hero-copy">
        <h1>Foot rot runs downhill with the rain. PepperDex sees where it goes next.</h1>
        <p className="lede">
          An early warning app for Sarawak’s black pepper smallholders. Photograph a vine, and a team of AI
          agents works out which blocks the runoff will reach, when the next rain comes, and the one thing to
          do today.
        </p>
        <div className="hero-actions">
          <a className="btn btn-primary" href="#get">Download for Android</a>
          <a className="btn btn-ondark" href="#get-demo">Try the demo farm</a>
        </div>
      </div>
    </section>
  );
}

function Problem() {
  return (
    <section className="problem" aria-labelledby="problem-h">
      <div className="wrap two-col">
        <div>
          <h2 id="problem-h">A catchment-scale disease, fought with single-plant tools.</h2>
          <p>
            Sarawak grows <strong>over 98%</strong> of Malaysia’s pepper on <strong>36,682</strong> registered
            smallholdings, mostly on hill slopes planted that way for drainage. The same runoff that keeps the
            vines dry carries <em>Phytophthora capsici</em> from block to block. An outbreak kills over 30% of
            vines and costs about <strong>USD 902 a hectare</strong>, more than half a smallholder’s yearly
            return.
          </p>
          <p className="pull">Water, not distance, decides which vine is next.</p>
        </div>
        <ul className="failures">
          {FAILURES.map((f) => (
            <li key={f.title}>
              <h3>{f.title}</h3>
              <p>{f.text}</p>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function Method() {
  const [open, setOpen] = useState('L2');
  return (
    <section className="method" id="method" aria-labelledby="method-h">
      <div className="wrap">
        <h2 id="method-h">Four kinds of evidence. None of them decides alone.</h2>
        <p className="section-lede">
          Each signal on its own gives bad advice. A photo says treat now; the rules say the drench needs a dry
          day; the forecast says rain tomorrow; the slope says the block below is next. PepperDex weighs them
          together and returns one action, one time and one reason for each block.
        </p>

        <div className="converge">
          <ol className="evidence">
            {EVIDENCE.map((e) => (
              <li key={e.name}>
                <h3>{e.name}</h3>
                <span className="src">{e.source}</span>
                <p>{e.gives}</p>
              </li>
            ))}
          </ol>
          <svg className="converge-lines" viewBox="0 0 100 400" preserveAspectRatio="none" aria-hidden="true">
            {[50, 150, 250, 350].map((y) => (
              <path key={y} d={`M0,${y} C55,${y} 45,200 100,200`} />
            ))}
          </svg>
          <div className="verdict">
            <span className="verdict-by">Router agent</span>
            <p>Clear the drain today. Drench Thursday morning.</p>
          </div>
        </div>

        <div className="guards">
          <h3>Checks around the agent</h3>
          <p className="guards-lede">
            A language model can be wrong. These checks are plain code and run on every plan, so a model
            mistake never reaches the farmer as advice.
          </p>
          <dl>
            {GUARDS.map((g) => (
              <div key={g.name}>
                <dt>{g.name}</dt>
                <dd>{g.text}</dd>
              </div>
            ))}
          </dl>
        </div>

        <div className="layers">
          <h3>Five layers, from voice to agents</h3>
          <div className="stack">
            {LAYERS.map((l) => {
              const isOpen = open === l.id;
              return (
                <div key={l.id} className={`slab${isOpen ? ' is-open' : ''}`}>
                  <button
                    type="button"
                    aria-expanded={isOpen}
                    aria-controls={`layer-${l.id}`}
                    onClick={() => setOpen(isOpen ? '' : l.id)}
                  >
                    <span className="slab-id">{l.id}</span>
                    <span className="slab-name">{l.name}</span>
                    <span className="slab-short">{l.short}</span>
                  </button>
                  <div id={`layer-${l.id}`} className="slab-body" hidden={!isOpen}>
                    <p>{l.detail}</p>
                    <p className="tech">{l.tech}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}

function Agents() {
  const [sel, setSel] = useState<AgentNode>(ROUTER);
  const node = (n: AgentNode, extra = '') => (
    <button
      type="button"
      className={`node ${extra}${sel.id === n.id ? ' is-sel' : ''}`}
      aria-pressed={sel.id === n.id}
      onClick={() => setSel(n)}
    >
      <span className="node-name">{n.name}</span>
      <span className="node-kind">{n.kind}</span>
    </button>
  );

  return (
    <section className="agents" id="agents" aria-labelledby="agents-h">
      <div className="wrap">
        <h2 id="agents-h">One router, specialist agents, and a council for the bad days.</h2>
        <p className="section-lede">
          Select an agent to see what it does. Deterministic tools do the arithmetic; the agents decide which
          tool to trust, and when.
        </p>

        <div className="agent-grid">
          <div className="tree">
            <div className="tree-top">
              {node(ROUTER, 'node-root')}
              <ul className="tools" aria-label="Deterministic tools the router calls">
                {TOOLS.map((t) => <li key={t}>{t}</li>)}
              </ul>
            </div>
            <div className="tree-kids">
              {SUBAGENTS.map((s) => (
                <div key={s.id} className="kid">
                  {node(s)}
                  {s.id === 'council' && (
                    <ul className="council-mini" aria-label="Council members">
                      <li>Agronomic urgency</li>
                      <li>Cost feasibility</li>
                      <li>Logistics</li>
                      <li className="orch">Orchestrator ranks</li>
                    </ul>
                  )}
                </div>
              ))}
            </div>
            <div className="tree-mcp">{node(CALENDAR, 'node-mcp')}</div>
          </div>

          <aside className="agent-detail" aria-live="polite">
            <span className="node-kind">{sel.kind}</span>
            <h3>{sel.name}</h3>
            <p>{sel.text}</p>
          </aside>
        </div>

        <div className="feed-block">
          <div className="feed-copy">
            <h3>You can watch them work</h3>
            <p>
              A diagnosis is not a spinner. After the photo round, the app’s chat shows each agent’s real step
              as it happens, under its own name. Every message comes from a tool result or a council
              transcript, never from a model describing itself afterwards. Tap any message to hear it.
            </p>
          </div>
          <ol className="feed" aria-label="Example activity feed">
            {FEED.map((f, i) => (
              <li key={i} className={f.agent === 'Router agent' ? 'is-final' : ''}>
                <span className="feed-agent">{f.agent}</span>
                <p>{f.text}</p>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}

function Council() {
  // 0 idle · 1–3 voices speaking · 4 ranked
  const [phase, setPhase] = useState(0);
  const timers = useRef<number[]>([]);
  useEffect(() => () => timers.current.forEach(clearTimeout), []);

  const run = () => {
    timers.current.forEach(clearTimeout);
    setPhase(0);
    const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const step = still ? 0 : 1100;
    [1, 2, 3, 4].forEach((p) => timers.current.push(window.setTimeout(() => setPhase(p), 200 + step * (p - 1))));
  };

  const rankOf = (id: string) => COUNCIL_RANKING.findIndex((r) => r.id === id);

  return (
    <section className="council" id="council" aria-labelledby="council-h">
      <div className="wrap">
        <h2 id="council-h">When more than one block is Harmed, the council ranks them.</h2>
        <p className="section-lede">
          The farm is Overrun and there is only time and money for one block at a time. Three agents argue
          from different angles, and an orchestrator puts the blocks in order. This only happens during an
          outbreak, never in a normal check.
        </p>

        <div className="council-stage">
          <div className="triage">
            <ol className={`triage-list${phase === 4 ? ' is-ranked' : ''}`} aria-label="Harmed blocks">
              {TRIAGE_BLOCKS.map((b, i) => {
                const r = phase === 4 ? rankOf(b.id) : i;
                return (
                  <li key={b.id} style={{ transform: `translateY(${r * 76}px)` }}>
                    <span className="rank">{phase === 4 ? r + 1 : ''}</span>
                    <span className="tb-name">{b.name}</span>
                    <span className="tb-note">
                      {phase === 4 ? COUNCIL_RANKING[r].why : b.note}
                    </span>
                  </li>
                );
              })}
            </ol>
            <button type="button" className="btn btn-primary" onClick={run} disabled={phase > 0 && phase < 4}>
              {phase === 4 ? 'Run it again' : 'Run the triage'}
            </button>
          </div>

          <ol className="voices" aria-live="polite">
            {COUNCIL_VOICES.map((v, i) => (
              <li key={v.agent} className={phase > i ? 'is-on' : ''}>
                <span className="voice-agent">{v.agent}</span>
                <p>{phase > i ? v.says : '…'}</p>
              </li>
            ))}
          </ol>

          <div className="wall">
            <h3>It can reorder. It cannot prescribe.</h3>
            <p>
              The council’s answer must fit this shape. There is no field for a product, a dose or a time, so a
              treatment cannot leave the council even if a model invents one.
            </p>
            <pre aria-label="TriageRanking schema"><code>{`class TriageRanking:
    block_id: str
    rank: int          # 1 = first
    rationale_ms: str  # ≤ 300 chars
    # extra fields rejected`}</code></pre>
          </div>
        </div>
      </div>
    </section>
  );
}

function Flow() {
  return (
    <section className="flow" aria-labelledby="flow-h">
      <div className="wrap">
        <h2 id="flow-h">From first open to an approved schedule.</h2>
        <ol className="steps">
          {FLOW.map((s, i) => (
            <li key={s.title}>
              <span className="step-n" aria-hidden="true">{i + 1}</span>
              <h3>{s.title}</h3>
              <p>{s.text}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

type Release = { versionName?: string; versionCode?: number; builtAt?: string; sizeMB?: number };

function GetApp() {
  const [qr, setQr] = useState('');
  const [rel, setRel] = useState<Release | null>(null);

  useEffect(() => {
    QRCode.toString(APK_URL, { type: 'svg', margin: 0, errorCorrectionLevel: 'M', color: { dark: '#15251B', light: '#FFFFFF' } })
      .then(setQr)
      .catch(() => setQr(''));
    // Written by the release script next to the APK; absent during local dev.
    fetch('/version.json', { cache: 'no-store' })
      .then((r) => (r.ok ? r.json() : null))
      .then(setRel)
      .catch(() => setRel(null));
  }, []);

  const built = rel?.builtAt
    ? new Date(rel.builtAt).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'Asia/Kuching' })
    : null;

  return (
    <section className="get" id="get" aria-labelledby="get-h">
      <div className="wrap get-grid">
        <div className="qr-card">
          <div className="qr" aria-label="QR code linking to the PepperDex Android app" role="img"
            dangerouslySetInnerHTML={{ __html: qr }} />
          <a className="btn btn-primary btn-block" href={APK_PATH} download>
            Download PepperDex{rel?.sizeMB ? ` (${rel.sizeMB} MB)` : ''}
          </a>
          <p className="release">
            {rel?.versionCode
              ? `Build ${rel.versionCode}${built ? `, ${built}` : ''}. Android 7 or newer.`
              : 'Android 7 or newer.'}
          </p>
        </div>

        <div>
          <h2 id="get-h">Install it on an Android phone.</h2>
          <ol className="install" id="get-demo">
            <li>Scan the code, or tap Download on the phone itself.</li>
            <li>When Android asks, allow your browser to install apps. PepperDex is not on the Play Store yet.</li>
            <li>Open PepperDex and tap <strong>Try the demo farm</strong>. It is a ready-made farm with diagnoses, agents at work and a 3D view of the slope, and it needs no setup.</li>
          </ol>
          <p className="aside">Only Android for now. The app talks to our server, so any mobile data or Wi-Fi works.</p>

          <ul className="shortcuts">
            <li><a href={REPO_URL} target="_blank" rel="noreferrer">Source code on GitHub</a></li>
            <li><a href={API_DOCS_URL} target="_blank" rel="noreferrer">API documentation</a></li>
            <li>
              {DEMO_VIDEO_URL
                ? <a href={DEMO_VIDEO_URL} target="_blank" rel="noreferrer">Demo video</a>
                : <span className="soon" aria-disabled="true">Demo video (coming soon)</span>}
            </li>
          </ul>
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="footer">
      <div className="wrap footer-inner">
        <img src="brand/logo.png" alt="PepperDex Sarawak" width="140" height="59" />
        <div>
          <p className="promise">
            No land boundaries are ever recorded. Every risk number is an estimate. Nothing reaches your calendar
            or your neighbours without your tap.
          </p>
          <p className="meta">
            Built for AgroHack 2026 at Sarawak AgroFest, Sibu, 25 to 27 September 2026, by team SMILING FACE WITH
            SUNGLASSES: Nathan, Zoe and Abraham.
          </p>
          <p className="meta"><i>Dari hulu ke hilir, sebelum penyakit sampai.</i> From upstream to downstream, before the disease arrives.</p>
        </div>
      </div>
    </footer>
  );
}
