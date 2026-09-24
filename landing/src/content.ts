/// Landing page copy, condensed from LANDING_PAGE.md (the source of truth).
///
/// Figures are the ones cited there -- claims from the literature, not
/// measurements this project made. The spread model is physically motivated
/// and not field-validated, which is why every risk number on this page, like
/// in the app, is marked as an estimate.

export const SITE_URL = 'https://sfws-aicc-workspace-1.web.app';
/// Fixed name: the release script overwrites this file on every build, so the
/// QR code printed on the bunting never goes stale.
export const APK_PATH = '/pepperdex-latest.apk';
export const APK_URL = `${SITE_URL}${APK_PATH}`;
export const REPO_URL = 'https://github.com/nathanyap17/huluhilir';
export const API_DOCS_URL = 'https://huluhilir-api-mfrzixfqeq-as.a.run.app/docs';
/// Empty until the video is published; the button shows as "coming soon".
export const DEMO_VIDEO_URL = '';

export const STATE = {
  protected: { label: 'Protected', colour: '#4F8A5B', rule: 'A confident healthy photo, or no risk reaching it' },
  alerted: { label: 'Alerted', colour: '#C98A1E', rule: 'Runoff from a diseased block is projected to reach it' },
  harmed: { label: 'Harmed', colour: '#B2422A', rule: 'A photo shows collar lesion or wilt' },
  overrun: { label: 'Overrun', colour: '#7A2E24', rule: 'More than one block Harmed at once' },
} as const;

export const FAILURES = [
  {
    title: 'Seen too late',
    text: 'The pathogen attacks the collar and roots first. By the time the leaves yellow, the vine is usually lost.',
  },
  {
    title: 'Blind to the slope',
    text: 'Runoff crosses from block to block. A farmer cannot tell whether the water coming down tonight is carrying disease.',
  },
  {
    title: 'Sprayed into the rain',
    text: 'Contact fungicides wash off. Spraying two days before a downpour sends the money, and the chemical, into the soil.',
  },
];

export const EVIDENCE = [
  { name: 'What is on the vine', source: 'Photo classifier', gives: 'A class and a confidence per block. Below 60% means “go and look”, never a diagnosis.' },
  { name: 'Where the water goes', source: 'Downhill graph', gives: 'Risk, path and arrival in days for every block below a sick one. Always labelled an estimate.' },
  { name: 'When the rain comes', source: 'data.gov.my forecast', gives: 'The next rain pulses and the dry windows between them, up to 7 days out.' },
  { name: 'What is allowed', source: 'Rules table (MPB, DOA Sarawak)', gives: 'The only source of product, dose and rain-fast hours. Six treatments.' },
];

export const GUARDS = [
  { name: 'Rain-fast check', text: 'A spray or drench is moved to a real dry window, or deferred behind drain clearing.' },
  { name: 'Rules check', text: 'Unknown products, invented blocks and stale dates are dropped. A sick block with no plan gets its rules-table action back.' },
  { name: 'Real spread numbers', text: 'The spread model is deterministic, so it runs for every diseased block. Risk is never a placeholder.' },
  { name: 'Fallback', text: 'If the language model is slow or fails, the rules table decides alone, and the app says so.' },
];

export const LAYERS = [
  {
    id: 'L4',
    name: 'Agents',
    short: 'Arbitrates everything below into one plan',
    detail:
      'A router agent calls the tools, weighs rain against spread against the rules, and hands work to specialists: the setup wizard, the diagnosis coordinator, the Advisor, and the Overrun Council. Every tool call is logged, so each plan has a readable trail.',
    tech: 'Google ADK · Gemini 2.5 Flash on Vertex AI (Qwen 2.5 14B offline)',
  },
  {
    id: 'L3',
    name: 'Knowledge',
    short: 'Rules decide what; documents explain why',
    detail:
      'A rules table from Malaysian Pepper Board and DOA Sarawak guidance fixes product, dose and rain-fast hours. A search over 23 disease-management documents (meaning plus keyword) explains the reasoning. It can never pick a treatment.',
    tech: 'JSON rules · hybrid retrieval · farm-history queries',
  },
  {
    id: 'L2',
    name: 'Spread',
    short: 'Water, not distance, decides exposure',
    detail:
      'Blocks become nodes in a directed downhill graph built from the setup walk: GPS, the barometer where the phone has one, and the farmer’s own “which is higher?” answers, which always win. From a confirmed case it projects risk, path and arrival for every block below.',
    tech: 'Deterministic graph · no machine learning · no land boundaries stored',
  },
  {
    id: 'L1',
    name: 'Diagnosis',
    short: 'Catches the collar lesion before the leaves turn',
    detail:
      'A small image classifier trained on six classes looks for the earliest visible sign of foot rot at the stem base. A photo of the wrong target prompts a retake; the farmer can always override.',
    tech: 'MobileNetV3-Small · ONNX · six classes',
  },
  {
    id: 'L0',
    name: 'Voice & language',
    short: 'Everything can be heard, nothing is transcribed',
    detail:
      'Advice, agent messages and the forecast can be played aloud in Bahasa Malaysia. Each block has a spoken name the farmer records, which is stored and replayed, never turned into text. The interface is in Bahasa Malaysia or English.',
    tech: 'Pre-recorded clips · MMS-TTS · no speech recognition',
  },
];

export type AgentNode = {
  id: string;
  name: string;
  kind: string;
  text: string;
};

export const ROUTER: AgentNode = {
  id: 'router',
  name: 'Router agent',
  kind: 'Arbitrator',
  text:
    'Reads every signal, calls the tools, and decides one action, one time and one reason per block. It routes a question to the Advisor, a setup to the wizard, a photo round to the coordinator, and an outbreak to the council.',
};

export const SUBAGENTS: AgentNode[] = [
  {
    id: 'setup',
    name: 'Setup wizard',
    kind: 'Loop agent',
    text:
      'Walks the farmer round the farm once: mark each block, take a photo, record its spoken name, answer a few “which is higher?” questions. Stops only when a valid downhill graph exists, with a hard limit on steps.',
  },
  {
    id: 'diagnosis',
    name: 'DiagnosisCoordinator',
    kind: 'Loop agent',
    text:
      'Guides the photo round block by block, checks each photo shows the right part of the vine, asks for a retake if not, and reports the results when every block is done.',
  },
  {
    id: 'advisor',
    name: 'Advisor',
    kind: 'Conversational agent',
    text:
      'Answers questions like “Are my blocks safer now?” from a live snapshot of the farm: states, the last two diagnoses, the current plan, projected spread, rain and pending schedules. General questions go to the knowledge base. It never states a dose itself.',
  },
  {
    id: 'council',
    name: 'Overrun Council',
    kind: 'Multi-agent triage',
    text:
      'Only wakes when more than one block is Harmed at once. Three agents argue from urgency, cost and logistics; an orchestrator ranks the blocks. Its output has no field that could hold a treatment.',
  },
];

export const TOOLS = ['get_weather', 'compute_spread', 'get_treatment', 'find_spray_window', 'query_farm_history'];

export const CALENDAR: AgentNode = {
  id: 'calendar',
  name: 'Google Calendar',
  kind: 'MCP server',
  text:
    'The agents may read the calendar to avoid clashes. Writing is not an agent tool at all: each spray, drench or drain clearing becomes a proposal card, and only the farmer’s Approve tap puts it on the calendar.',
};

export type TriageBlock = { id: string; name: string; note: string };

export const TRIAGE_BLOCKS: TriageBlock[] = [
  { id: 'b2', name: 'Block 2', note: 'Collar lesion, 88%' },
  { id: 'b4', name: 'Block 4', note: 'Wilt, 74%' },
  { id: 'b5', name: 'Block 5', note: 'Collar lesion, 91%' },
];

/// Illustrative debate, written in the shape of a real council transcript.
export const COUNCIL_VOICES = [
  {
    agent: 'Agronomic urgency',
    says: 'Block 5 sits at the top of the slope. Everything below it gets its runoff at the next rain. Block 5 first.',
  },
  {
    agent: 'Cost feasibility',
    says: 'Block 4 is already wilting; saving it costs the most for the least. Spend on 5 and 2 before 4.',
  },
  {
    agent: 'Logistics',
    says: 'Blocks 5 and 2 share a path and a water source. One trip covers both before the rain on Thursday.',
  },
];

export const COUNCIL_RANKING = [
  { id: 'b5', why: 'Upslope source; protects everything below' },
  { id: 'b2', why: 'Same trip as Block 5' },
  { id: 'b4', why: 'Lowest chance of recovery' },
];

export const FLOW = [
  { title: 'Open the app', text: 'Try the ready-made demo farm, set up your own, or restore one with the private code from your old phone.' },
  { title: 'Walk the farm once', text: 'Tap to mark each block, photograph it, say its name. Answer which block is higher; your answer beats the sensors.' },
  { title: 'Read the home screen', text: 'The rain card, the one action to do next, and whether a check is due. All of it works before any photo is taken.' },
  { title: 'Photograph each block', text: 'The coordinator guides you block by block and asks for a retake if a photo shows the wrong part of the vine.' },
  { title: 'Watch the agents work', text: 'The chat fills with each agent’s real step: the photo results, rain, the spread, the rules, the decision.' },
  { title: 'Approve the schedule', text: 'Each action arrives as a card. Approve adds it to Google Calendar; Reject drops it. Nothing is written without your tap.' },
  { title: 'Ask what changed', text: '“Are my blocks safer now?” The Advisor compares this round with the last one, block by block.' },
];

export const FEED = [
  { agent: 'DiagnosisCoordinator', text: 'Block 1: collar lesion, 91%. Blocks 2–5 healthy.' },
  { agent: 'Weather', text: 'Heavy rain tomorrow, about 46 mm (estimate). Dry from Thursday 06:00.' },
  { agent: 'Spread', text: 'Runoff from Block 1 reaches Block 2 in ~2 days and Block 3 in ~4 days (estimates).' },
  { agent: 'Rules', text: 'Drench approved for collar lesion. Needs 24 h without rain.' },
  { agent: 'Router agent', text: 'Clear the drain below Block 1 today. Drench Thursday morning.' },
];
