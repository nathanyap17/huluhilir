"""explain_why and draft_alert -- LLM-backed FunctionTools, NOT agents.

huluhilir-rules skill §4: one prompt in, text out, no autonomy. Both call
complete_text() directly rather than running through the ADK agent loop.
Neither ever invents a dose/product/timing (explain_why only narrates facts
it's given; the rules table already decided those) or auto-sends an alert
(approved_by_farmer always defaults False).

*_flat functions are the ones actually registered as ADK tools -- flattened
scalar/dict parameters only, no nested Pydantic model as the whole parameter.
See app/agent/tools.py's module docstring for why that shape is required in
this installed ADK version. The non-flat explain_why/draft_alert remain the
internal Python API for reuse outside the agent (e.g. direct router calls).
"""
from app.agent.model import complete_text
from app.schemas.agent import DraftAlertRequest, DraftAlertResult, ExplainWhyRequest, ExplainWhyResult

EXPLAIN_WHY_SYSTEM = """Anda menulis SATU ayat sebab dalam Bahasa Malaysia untuk seorang petani lada hitam.
Gunakan HANYA fakta yang diberikan -- jangan cipta dos, produk, atau jangka masa baru.
Jangan gunakan istilah teknikal. Ayat mesti pendek dan jelas."""

DRAFT_ALERT_SYSTEM = """Anda menulis draf mesej amaran ringkas dalam Bahasa Malaysia untuk memberitahu
seorang petani jiran bahawa risiko penyakit dikesan berhampiran ladang mereka.
Kongsi HANYA tahap risiko (band) -- JANGAN sebut nama ladang sumber, jenis penyakit,
lokasi tepat, atau sebarang butiran diagnosis. Mesej mesti pendek, sopan, dan menggesa
petani menyemak blok mereka sendiri."""


async def explain_why(req: ExplainWhyRequest) -> ExplainWhyResult:
    """Internal API -- not registered as an ADK tool directly (see module docstring)."""
    facts_text = "\n".join(f"- {k}: {v}" for k, v in req.supporting_facts.items())
    prompt = (
        f"Cadangan: {req.recommendation.action_type} untuk blok {req.recommendation.block_id} "
        f"pada {req.recommendation.recommended_at}.\n"
        f"Fakta sokongan:\n{facts_text}\n\n"
        "Tulis SATU ayat sebab (maksimum 300 aksara) dalam Bahasa Malaysia."
    )
    reason = await complete_text(prompt, system=EXPLAIN_WHY_SYSTEM)
    return ExplainWhyResult(reason_ms=reason[:300])


async def draft_alert(req: DraftAlertRequest) -> DraftAlertResult:
    """Internal API -- not registered as an ADK tool directly (see module docstring)."""
    prompt = (
        f"Tahap risiko yang dikesan: {req.risk_band}.\n"
        "Tulis draf mesej amaran pendek (maksimum 2 ayat) untuk jiran."
    )
    message = await complete_text(prompt, system=DRAFT_ALERT_SYSTEM)
    return DraftAlertResult(message_ms=message, risk_band_shared=req.risk_band)


async def explain_why_flat(
    block_id: str, action_type: str, recommended_at: str, supporting_facts: dict[str, str]
) -> ExplainWhyResult:
    """Render the one-sentence reason for a recommendation in plain Bahasa
    Malaysia, using only the supplied facts (e.g. diagnosis class, rainfast
    hours, forecast mm, spread eta_days). Call this for every recommendation
    the root agent produces -- never invent the reason yourself.
    supporting_facts is a flat dict of fact_name -> value as strings."""
    req = ExplainWhyRequest(
        recommendation=_dummy_recommendation(block_id, action_type, recommended_at),
        supporting_facts=supporting_facts,
    )
    return await explain_why(req)


async def draft_alert_flat(target_block_id: str, risk_band: str, source_farm_name: str) -> DraftAlertResult:
    """Draft (never send) a neighbour alert sharing only the risk band. Call
    this when a downslope block belongs to another farmer -- the message is
    always saved with approved_by_farmer=False and status=draft.
    risk_band is one of 'protected','alerted','harmed','overrun'."""
    req = DraftAlertRequest(target_block_id=target_block_id, risk_band=risk_band, source_farm_name=source_farm_name)
    return await draft_alert(req)


def _dummy_recommendation(block_id: str, action_type: str, recommended_at: str):
    from app.schemas.agent import RecommendationOut
    return RecommendationOut(
        run_id="pending", block_id=block_id, sequence=1, action_type=action_type,
        recommended_at=recommended_at, reason_ms="pending",
    )
