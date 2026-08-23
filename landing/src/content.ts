/// Landing page copy, condensed from LANDING_PAGE.md.
///
/// Figures here are the ones cited in that document; they are claims from the
/// literature it references, not measurements this project made. The spread
/// model itself is physically motivated and explicitly not field-validated,
/// which is why the app flags every risk number it emits as an estimate.

/// The Flutter web build is served from /app on the same Firebase Hosting
/// site, so this stays a relative path and keeps working if the domain
/// changes.
export const APP_URL = '/app/';
export const REPO_URL = 'https://github.com/nathanyapjiade/huluhilir';
export const API_DOCS_URL = 'https://huluhilir-api-mfrzixfqeq-as.a.run.app/docs';

export const STATS = [
  { value: 98, suffix: '%', label: 'of Malaysia’s pepper production comes from Sarawak' },
  { value: 36682, suffix: '', label: 'registered smallholder farms on sloped terrain' },
  { value: 30, suffix: '%+', label: 'vine mortality when an outbreak takes hold' },
  { value: 56, suffix: '%', label: 'of a smallholder’s annual net returns lost — USD 902/ha' },
];

export const SIGNALS = [
  {
    source: 'L1 · Diagnosis',
    text: 'Collar lesion detected on an upslope block.',
    colour: '#cc7a5c',
  },
  {
    source: 'L3 · Treatment rules',
    text: 'This fungicide needs a 24-hour rain-fast window.',
    colour: '#5a5a40',
  },
  {
    source: 'Weather',
    text: '46 mm of rain forecast tomorrow afternoon.',
    colour: '#6c86a8',
  },
  {
    source: 'L2 · Spread',
    text: 'Downslope block reached in roughly 4 days.',
    colour: '#ebc366',
  },
];

export const LAYERS = [
  {
    id: 'L0',
    title: 'Voice & language',
    body: 'Every prompt, diagnosis and recommendation is speakable in Bahasa Malaysia — literacy is not assumed. Voice labels are recorded and replayed as audio, never transcribed, which is exactly why Iban works here despite no reliable Iban speech recognition existing.',
  },
  {
    id: 'L1',
    title: 'Diagnosis — MobileNetV3-Small',
    body: 'Six classes, trained to catch collar lesions: the dark, water-soaked tissue at the stem base that is the earliest treatable signature. By the time leaves yellow, the vine is usually already lost. Macro F1 0.934.',
  },
  {
    id: 'L2',
    title: 'Spread — a directed elevation graph',
    body: 'Deliberately not machine learning. Blocks are nodes ordered by relative elevation; edges are downslope water paths. Combined with rainfall, this projects which block is reached, and roughly when. Every number it emits is flagged as an estimate.',
  },
  {
    id: 'L3',
    title: 'Knowledge — rules, then retrieval',
    body: 'Dose, product and timing come only from a deterministic rules table compiled from MPB and DOA Sarawak guidance. Retrieval explains why; it can never decide what — the advisor’s only tool is scoped away from that table entirely.',
  },
  {
    id: 'L4',
    title: 'Agent — the arbitrator',
    body: 'A Google ADK root agent over deterministic tools, two bounded loop agents and an advisor. Loop termination is deterministic Python querying the database, never model judgement: the LLM chooses which template to speak, not whether a cycle is finished.',
  },
];

export const RULES = [
  {
    title: 'No land boundaries are recorded',
    body: 'Only relative elevation ordering. Much of Sarawak’s pepper grows on Native Customary Rights land, where boundary mapping is legally sensitive and a reason not to trust an app.',
  },
  {
    title: 'Neighbour alerts are drafted, never sent',
    body: 'Only a risk band is ever shared, and approval defaults to false. The system cannot notify anyone about a farmer’s land on the farmer’s behalf.',
  },
  {
    title: 'The farmer overrides the sensor',
    body: 'When a barometer and the farmer disagree about which block is uphill, the farmer wins. The conflict is logged, never silently resolved against them.',
  },
  {
    title: 'It works with zero photographs',
    body: 'Rain-pulse warnings and the advisor run before any diagnosis cycle exists. Nothing on the dashboard is gated behind taking a picture.',
  },
  {
    title: 'No speech recognition on the critical path',
    body: 'Voice input is stored and replayed as audio. Off-the-shelf recognition for Iban and Sarawak Malay is not dependable enough to sit between a farmer and their advice.',
  },
  {
    title: 'Every risk figure is marked an estimate',
    body: 'The spread model is physically motivated but has not been field-validated. Presenting its output as measurement would be the easiest and worst shortcut available.',
  },
];
