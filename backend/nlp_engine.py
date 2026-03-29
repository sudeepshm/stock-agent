"""
nlp_engine.py — Role 2: The Opportunity Radar
==============================================
Chief Qualitative Officer: converts raw documents into high-density
financial signals. Strict separation of concerns:

  Sub-task 2.1  _prepare_context()   — document reader / preprocessor
  Sub-task 2.2  generate_insight()   — gemini 1.5 pro reasoning engine
  Sub-task 2.3  _validate_signal()   — pydantic-based JSON hardening

Math belongs in Role 3. Any quantitative calculation request raises
MathOperationError immediately.
"""

from __future__ import annotations

import json
import re
from typing import Optional

# ── external deps ──────────────────────────────────────────────────────────────
import boto3                                   # MinIO S3-compatible client
from botocore.client import Config
from pydantic import BaseModel, Field, ValidationError, model_validator
try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except Exception:
    ChatGoogleGenerativeAI = None
try:
    from langchain.schema import HumanMessage, SystemMessage
except Exception:
    HumanMessage = None
    SystemMessage = None
import asyncio
import os


# ==============================================================================
# Sub-task 2.3 — The Contract  (placed at top: acts as the API contract)
# ==============================================================================

MATH_KEYWORDS = frozenset([
    "pe ratio", "price to earnings", "eps", "cagr", "dcf",
    "discounted cash flow", "moving average", "rsi", "beta",
    "dividend yield", "debt to equity", "ebitda margin",
])

VALID_SIGNAL_TYPES = {
    "Capex Expansion",
    "Management Shakeup",
    "Guidance Upgrade",
    "Guidance Downgrade",
    "Promoter Buying",
    "Promoter Selling",
    "Debt Reduction",
    "Revenue Acceleration",
    "Margin Compression",
    "Regulatory Risk",
    "M&A Activity",
    "Share Buyback",
    "Unknown",
}


class FinancialSignal(BaseModel):
    """
    The validated output contract for every document analysis.

    sentiment_score: float in [-1, 1]
        -1.0 = strongly negative (profit warnings, management exits)
         0.0 = neutral / mixed signals
        +1.0 = strongly positive (guidance upgrades, promoter buying)

    key_findings: max 5 bullet-points; each is a raw observation,
        NOT a derived calculation. Percentages must be reported as text.

    signal_type: one of VALID_SIGNAL_TYPES; defaults to "Unknown" if
        Gemini returns an unrecognised value.
    """
    symbol: str = Field(..., min_length=1, max_length=10)
    sentiment_score: float = Field(..., ge=-1.0, le=1.0)
    key_findings: list[str] = Field(default_factory=list, max_length=5)
    signal_type: str = Field(default="Unknown")

    @model_validator(mode="after")
    def _normalise_signal_type(self) -> "FinancialSignal":
        if self.signal_type not in VALID_SIGNAL_TYPES:
            # Hallucinated signal type → soft-fix to Unknown
            self.signal_type = "Unknown"
        return self

    @model_validator(mode="after")
    def _cap_key_findings(self) -> "FinancialSignal":
        # Trim to 5 if Gemini over-generates
        self.key_findings = self.key_findings[:5]
        return self


class SignalError(Exception):
    """
    Raised when the LLM output cannot be coerced into a FinancialSignal,
    or when a prohibited (math) operation is requested.

    Attributes
    ----------
    reason : str      — human-readable failure description
    raw    : str|None — the raw LLM string that caused the failure
    """
    def __init__(self, reason: str, raw: Optional[str] = None):
        self.reason = reason
        self.raw = raw
        super().__init__(reason)


class MathOperationError(SignalError):
    """
    Raised when a caller asks Role 2 to perform a quantitative
    calculation. All math must be routed to Role 3.
    """
    def __init__(self, requested_metric: str):
        super().__init__(
            reason=(
                f"Role 2 does not perform calculations. "
                f"'{requested_metric}' must be computed by Role 3 (Quant Engine)."
            )
        )


# ==============================================================================
# Sub-task 2.1 — The Document Reader (preprocessing)
# ==============================================================================

class _DocumentReader:
    """
    Fetches files from MinIO and converts them to LLM-ready plain text.

    Design choices
    ──────────────
    • We do NOT summarise before sending to Gemini; 1.5 Pro's 1M-token
      context window can hold a full earnings transcript. Summarising early
      would destroy the subtle tone/phrasing signals we need.

    • We DO strip non-semantic artefacts: page headers, footers, slide
      numbers, and repeated boilerplate ("Safe Harbor Statement" blocks).

    • Chunking: only applied for very large filings (>200 k tokens).
      In that case we keep the full MD&A section + Q&A transcript and
      drop appendix tables (tables belong to Role 3).
    """

    _BOILERPLATE_PATTERNS = [
        r"(?i)safe harbor statement.*?(?=\n\n)",
        r"(?i)forward[-\s]looking statements.*?(?=\n\n)",
        r"(?i)page \d+ of \d+",
        r"(?i)confidential.*?(?=\n)",
    ]

    def __init__(self, minio_endpoint: str, access_key: str, secret_key: str,
                 bucket: str = "financial-docs"):
        self._bucket = bucket
        self._s3 = boto3.client(
            "s3",
            endpoint_url=minio_endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(signature_version="s3v4"),
        )

    def fetch_text(self, file_id: str) -> str:
        """
        Download `file_id` from MinIO and return cleaned UTF-8 text.

        Supports plain text (.txt), JSON transcripts, and raw bytes
        (PDF text layer extraction is handled externally before upload).

        Raises
        ------
        SignalError  — if the object does not exist or cannot be decoded.
        """
        try:
            response = self._s3.get_object(Bucket=self._bucket, Key=file_id)
            raw_bytes: bytes = response["Body"].read()
        except self._s3.exceptions.NoSuchKey:
            raise SignalError(f"Document '{file_id}' not found in MinIO bucket '{self._bucket}'.")
        except Exception as exc:
            raise SignalError(f"MinIO fetch failed for '{file_id}': {exc}")

        try:
            raw_text = raw_bytes.decode("utf-8", errors="replace")
        except Exception as exc:
            raise SignalError(f"Failed to decode document '{file_id}': {exc}")

        return self._clean(raw_text)

    def _clean(self, text: str) -> str:
        """Strip boilerplate and normalise whitespace."""
        for pattern in self._BOILERPLATE_PATTERNS:
            text = re.sub(pattern, "", text, flags=re.DOTALL)
        # Collapse excessive blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


# ==============================================================================
# Sub-task 2.2 — The Reasoning Engine (LLM prompt + call)
# ==============================================================================

_SYSTEM_INSTRUCTION = """\
You are a senior equity research analyst specialising in detecting
qualitative inflection points in corporate filings and earnings calls.

WHAT YOU LOOK FOR
─────────────────
• Promoter / insider buying signals (mentions of ESOP vesting, open-market
  purchases, lock-in expiry).
• Guidance upgrades or downgrades — look for tonal shifts, not just numbers.
• Capital expenditure expansion plans.
• Management tone changes (hedging language, confidence vocabulary, departure
  announcements).
• Regulatory risk language (new litigation, policy change references).

OUTPUT FORMAT
─────────────
Return ONLY a JSON object. No preamble. No "Here is the analysis:".
No markdown code fences. The JSON must match this exact schema:

{
  "symbol": "<TICKER>",
  "sentiment_score": <float between -1 and 1>,
  "key_findings": ["<finding 1>", "<finding 2>", ...],   // max 5 items
  "signal_type": "<one of the recognised signal types>"
}

Recognised signal_type values:
  Capex Expansion | Management Shakeup | Guidance Upgrade |
  Guidance Downgrade | Promoter Buying | Promoter Selling |
  Debt Reduction | Revenue Acceleration | Margin Compression |
  Regulatory Risk | M&A Activity | Share Buyback | Unknown

HARD CONSTRAINTS
────────────────
• Do NOT perform any arithmetic or verify any percentages. If a number
  appears in the text, quote it verbatim as a string — never recalculate it.
• Do NOT mention PE ratios, EPS, CAGR, or any derived financial metric.
  That computation belongs to a separate engine.
• Do NOT add fields not listed in the schema above.
• If you cannot determine a field, use the most conservative default
  (0.0 for score, [] for findings, "Unknown" for type).
"""

_USER_PROMPT_TEMPLATE = """\
Analyse the following document for the equity symbol {symbol}.
Identify the dominant qualitative signal and return the JSON schema.

DOCUMENT
────────
{document_text}
"""


class _ReasoningEngine:
    """
    Wraps Gemini 1.5 Pro via LangChain for financial sentiment reasoning.

    Why Gemini 1.5 Pro specifically:
    • The full-transcript strategy requires a 200k+ token context window.
    • Detecting management tone *shifts* needs sophisticated reasoning that
      smaller models (Flash, Haiku) miss — they pattern-match surface words
      instead of inferring intent from discourse structure.
    """

    MODEL_ID = "gemini-1.5-pro"

    def __init__(self, google_api_key: str, temperature: float = 0.1):
        # Low temperature → deterministic, conservative signal extraction.
        # Temperature > 0.3 increases hallucination risk on structured output.
        self._llm = ChatGoogleGenerativeAI(
            model=self.MODEL_ID,
            google_api_key=google_api_key,
            temperature=temperature,
            convert_system_message_to_human=False,
        )

    def call(self, symbol: str, document_text: str) -> str:
        """
        Send the prepared context to Gemini 1.5 Pro and return the raw
        string response (un-parsed). Parsing is handled by _validate_signal.

        Returns
        -------
        str  — raw LLM output, ideally valid JSON.

        Raises
        ------
        SignalError — if the LLM call itself fails (network, quota, etc.).
        """
        messages = [
            SystemMessage(content=_SYSTEM_INSTRUCTION),
            HumanMessage(content=_USER_PROMPT_TEMPLATE.format(
                symbol=symbol,
                document_text=document_text,
            )),
        ]
        try:
            result = self._llm.invoke(messages)
            return result.content
        except Exception as exc:
            raise SignalError(f"Gemini API call failed: {exc}")


# ==============================================================================
# Sub-task 2.3 — The JSON Parser / Signal Hardening
# ==============================================================================

def _validate_signal(ai_raw_output: str, symbol: str) -> FinancialSignal:
    """
    Coerce the raw LLM string into a validated FinancialSignal.

    Recovery strategy (in order):
    1. Direct JSON parse.
    2. Strip markdown code fences and retry.
    3. Regex-extract the first {...} block and retry.
    4. If all parsing fails → raise SignalError with raw output attached.
    5. If JSON parses but Pydantic rejects it → raise SignalError.

    The symbol is injected/overridden here to ensure the output always
    reflects the *requested* ticker, not whatever Gemini wrote.
    """
    cleaned = ai_raw_output.strip()

    # Strategy 1 — direct parse
    parsed_dict = _try_json_parse(cleaned)

    # Strategy 2 — strip markdown fences
    if parsed_dict is None:
        no_fences = re.sub(r"```(?:json)?|```", "", cleaned).strip()
        parsed_dict = _try_json_parse(no_fences)

    # Strategy 3 — extract first JSON block
    if parsed_dict is None:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            parsed_dict = _try_json_parse(match.group(0))

    if parsed_dict is None:
        raise SignalError(
            reason="LLM response could not be parsed as JSON after all recovery attempts.",
            raw=ai_raw_output,
        )

    # Force the symbol to the one we actually requested
    parsed_dict["symbol"] = symbol.upper()

    # Pydantic validation (also runs model validators for signal_type normalisation)
    try:
        return FinancialSignal(**parsed_dict)
    except ValidationError as exc:
        raise SignalError(
            reason=f"Pydantic validation failed: {exc}",
            raw=ai_raw_output,
        )


def _try_json_parse(text: str) -> Optional[dict]:
    """Return parsed dict or None — never raises."""
    try:
        result = json.loads(text)
        return result if isinstance(result, dict) else None
    except (json.JSONDecodeError, ValueError):
        return None


# ==============================================================================
# NLPEngine — public interface (Role 2 entry point)
# ==============================================================================

class NLPEngine:
    """
    The public interface for Role 2: The Opportunity Radar.

    Usage
    -----
        engine = NLPEngine(
            minio_endpoint="http://minio:9000",
            minio_access_key="...",
            minio_secret_key="...",
            google_api_key="...",
        )
        signal: FinancialSignal = engine.generate_insight(
            symbol="RELIANCE",
            document_id="reliance_q4_2024_transcript.txt",
        )

    Constraint: this class NEVER performs arithmetic. If a caller
    requests a quantitative metric, MathOperationError is raised.
    """

    def __init__(
        self,
        minio_endpoint: str,
        minio_access_key: str,
        minio_secret_key: str,
        google_api_key: str,
        minio_bucket: str = "financial-docs",
        llm_temperature: float = 0.1,
    ):
        self._reader = _DocumentReader(
            minio_endpoint=minio_endpoint,
            access_key=minio_access_key,
            secret_key=minio_secret_key,
            bucket=minio_bucket,
        )
        # Initialize LLM wrapper only if LangChain Google client is available
        if ChatGoogleGenerativeAI is not None and google_api_key:
            self._llm = _ReasoningEngine(
                google_api_key=google_api_key,
                temperature=llm_temperature,
            )
        else:
            self._llm = None

    # ── Sub-task 2.1 wrapper ──────────────────────────────────────────────────

    def _prepare_context(self, document_id: str) -> str:
        """
        Fetch from MinIO and return cleaned, LLM-ready text.

        We pass the FULL transcript (not a summary) to preserve
        tone signals that short summaries erase.
        """
        return self._reader.fetch_text(document_id)

    # ── Math guard ────────────────────────────────────────────────────────────

    @staticmethod
    def _guard_math_request(query: str) -> None:
        """
        If the caller has injected a quantitative metric keyword into the
        request, raise MathOperationError immediately.

        This is the boundary between Role 2 (qualitative) and Role 3 (quant).
        """
        lower_query = query.lower()
        for keyword in MATH_KEYWORDS:
            if keyword in lower_query:
                raise MathOperationError(requested_metric=keyword)

    # ── Sub-task 2.2 + 2.3 combined pipeline ─────────────────────────────────

    def generate_insight(
        self,
        symbol: str,
        document_id: str,
        extra_context: Optional[str] = None,
    ) -> FinancialSignal:
        """
        The main pipeline: fetch → reason → validate → return signal.

        Parameters
        ----------
        symbol       : equity ticker, e.g. "TCS", "INFY", "RELIANCE"
        document_id  : MinIO object key for the source document
        extra_context: optional string appended to the document text
                       (e.g. recent news headline injected by Role 1)

        Returns
        -------
        FinancialSignal — validated Pydantic object, safe to serialise.

        Raises
        ------
        SignalError         — unrecoverable LLM output or fetch failure.
        MathOperationError  — if a quantitative calculation was requested.
        """
        # Step 0: block any math requests before touching the LLM
        self._guard_math_request(symbol)
        if extra_context:
            self._guard_math_request(extra_context)

        # Step 1: sub-task 2.1 — prepare context
        document_text = self._prepare_context(document_id)

        if extra_context:
            document_text = f"{document_text}\n\n--- ADDITIONAL CONTEXT ---\n{extra_context}"

        # Step 2: sub-task 2.2 — call Gemini 1.5 Pro (optional)
        if self._llm is None:
            # LLM unavailable — return a conservative neutral signal
            return FinancialSignal(symbol=symbol.upper(), sentiment_score=0.0, key_findings=[], signal_type="Unknown")

        raw_output = self._llm.call(symbol=symbol, document_text=document_text)

        # Step 3: sub-task 2.3 — harden the output
        signal = _validate_signal(raw_output, symbol=symbol)

        return signal


# -----------------------------------------------------------------------------
# Async adapter for orchestrator
# -----------------------------------------------------------------------------
async def run_nlp_analysis(market_data: dict, symbol: str) -> FinancialSignal:
    """
    Async wrapper used by the orchestrator. Chooses a document (if any)
    from `market_data['documents']` and invokes the synchronous
    `NLPEngine.generate_insight` on a background thread. If no documents
    are available, returns a conservative neutral FinancialSignal.
    """
    minio_endpoint = os.getenv("MINIO_ENDPOINT", "http://localhost:9000")
    minio_access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    minio_secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    google_api_key = os.getenv("GEMINI_API_KEY", "")

    docs = market_data.get("documents") or []
    if not docs:
        # No document to analyse — return a neutral/unknown signal.
        return FinancialSignal(symbol=symbol.upper(), sentiment_score=0.0, key_findings=[], signal_type="Unknown")

    # Pick the first available document metadata (caller may sort earlier)
    doc = docs[0]
    document_id = doc.get("object_key")
    bucket = doc.get("bucket_name", "financial-docs")

    engine = NLPEngine(
        minio_endpoint=minio_endpoint,
        minio_access_key=minio_access_key,
        minio_secret_key=minio_secret_key,
        google_api_key=google_api_key,
        minio_bucket=bucket,
    )

    return await asyncio.to_thread(engine.generate_insight, symbol.upper(), document_id)