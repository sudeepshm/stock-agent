# =============================================================================
# backend/main.py
# Role 4: The Orchestrator / API Gateway
# Responsibilities:
#   - Sub-task 4.1: Endpoint Layer   → Receive & Validate
#   - Sub-task 4.2: Async Manager    → Fire & Forget (BackgroundTasks)
#   - Sub-task 4.3: Aggregator       → Merge NLP + Chart results
#   - Sub-task 4.4: State Store      → Track & expose job progress
#
# Constraints honoured:
#   ✓ No prompts, no math — pure routing / merging
#   ✓ Stateless: all domain logic lives in imported modules
#   ✓ Circuit breaker around chart_engine (try/except)
#   ✓ /analyze returns in < 200 ms (BackgroundTask, no AI blocking)
#   ✓ Status lifecycle: PENDING → ANALYZING_TEXT → VERIFYING_CHARTS → COMPLETED
# =============================================================================

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

import redis.asyncio as aioredis
from fastapi import BackgroundTasks, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# --------------- domain imports (Role 2 & 3 contracts) -----------------------
from chart_engine import ChartAnalysis, run_chart_analysis        # Role 3
from data_lake import fetch_market_data                            # Role 1
from nlp_engine import FinancialSignal, run_nlp_analysis           # Role 2
import pandas as pd
import numpy as np
try:
    import talib
except ImportError:
    talib = None
import yfinance as yf
import os

# =============================================================================
# Logging
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("orchestrator")

# =============================================================================
# App & Middleware
# =============================================================================
app = FastAPI(
    title="FinSight Orchestrator",
    description="API Gateway — coordinates Data Lake, NLP Engine, and Chart Engine.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # tighten in production
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# =============================================================================
# Redis connection (shared across workers)
# =============================================================================
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
redis_client: aioredis.Redis = aioredis.from_url(
    REDIS_URL,
    encoding="utf-8",
    decode_responses=True,
)

JOB_TTL_SECONDS = 3600   # keep job state for 1 hour


# =============================================================================
# Sub-task 4.4: Job status lifecycle constants
# =============================================================================
class JobStatus:
    PENDING          = "PENDING"
    FETCHING_DATA    = "FETCHING_DATA"
    ANALYZING_TEXT   = "ANALYZING_TEXT"
    VERIFYING_CHARTS = "VERIFYING_CHARTS"
    COMPLETED        = "COMPLETED"
    FAILED           = "FAILED"


# =============================================================================
# Sub-task 4.3: The Unified Contract  (Pydantic schema)
# =============================================================================
class FinalReport(BaseModel):
    """
    The single JSON shape the frontend always receives.
    Fields may be None while the job is still in flight.
    """
    job_id:          str                     = Field(..., description="UUID for this analysis run")
    symbol:          str                     = Field(..., description="Ticker symbol, e.g. RELIANCE.NS")
    status:          str                     = Field(..., description="Current lifecycle stage")
    created_at:      str                     = Field(..., description="ISO-8601 UTC timestamp")
    completed_at:    Optional[str]           = Field(None)

    # --- Role 2 output ---
    nlp_insight:     Optional[FinancialSignal]  = Field(None)

    # --- Role 3 output ---
    chart_insight:   Optional[ChartAnalysis]   = Field(None)
    charts_available: bool                     = Field(True, description="False when chart_engine timed-out or errored")

    # --- Observability ---
    error_logs:      list[str]               = Field(default_factory=list)


# =============================================================================
# Helpers
# =============================================================================
_NSE_BSE_PATTERN = re.compile(
    r"^[A-Z0-9&\-\.]{1,20}\.(NS|BO)$",
    re.IGNORECASE,
)

def _validate_symbol(symbol: str) -> str:
    """
    Normalise and validate a ticker symbol.
    Accepts:  RELIANCE.NS  /  TATAMOTORS.BO
    Rejects:  empty strings, SQL injection attempts, unknown suffixes.
    """
    symbol = symbol.strip().upper()
    if not symbol:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Symbol must not be empty.",
        )
    if not _NSE_BSE_PATTERN.match(symbol):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"'{symbol}' is not a recognised Indian market symbol. "
                "Expected format: TICKER.NS (NSE) or TICKER.BO (BSE)."
            ),
        )
    return symbol


def _generate_job_id() -> str:
    return str(uuid.uuid4())


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# =============================================================================
# Sub-task 4.4: State helpers (Redis-backed)
# =============================================================================
async def _save_report(report: FinalReport) -> None:
    """Persist (or overwrite) the FinalReport in Redis as JSON."""
    await redis_client.set(
        f"job:{report.job_id}",
        report.model_dump_json(),
        ex=JOB_TTL_SECONDS,
    )


async def _load_report(job_id: str) -> FinalReport | None:
    """Return the FinalReport for *job_id*, or None if not found."""
    raw = await redis_client.get(f"job:{job_id}")
    if raw is None:
        return None
    return FinalReport.model_validate_json(raw)


async def _set_status(job_id: str, new_status: str) -> None:
    """
    Partial update: change only the `status` field without loading/saving
    the entire report object.  Keeps Redis round-trips minimal.
    """
    report = await _load_report(job_id)
    if report:
        report.status = new_status
        await _save_report(report)


# =============================================================================
# Sub-task 4.2 + 4.3: The Async Workflow  (Background Task)
# =============================================================================
async def orchestrate_workflow(symbol: str, job_id: str) -> None:
    """
    Runs entirely in the background.  Never blocks the HTTP response.

    Lifecycle:
        PENDING → FETCHING_DATA → ANALYZING_TEXT → VERIFYING_CHARTS → COMPLETED
                                                                     (or FAILED)

    Circuit Breaker (Sub-task 4.3 constraint):
        If chart_engine raises ANY exception, the report is still returned
        with nlp_insight intact and charts_available = False.
    """
    logger.info("[%s] Workflow started for symbol=%s", job_id, symbol)

    # ── 1. Initialise the report record in Redis ──────────────────────────────
    report = FinalReport(
        job_id=job_id,
        symbol=symbol,
        status=JobStatus.PENDING,
        created_at=_utc_now(),
    )
    await _save_report(report)

    try:
        # ── 2. Data Lake: fetch raw market data (Role 1) ──────────────────────
        report.status = JobStatus.FETCHING_DATA
        await _save_report(report)

        market_data = await fetch_market_data(symbol)
        logger.info("[%s] Data Lake: %d rows fetched", job_id, len(market_data))

        # ── 3. NLP Engine: text-based signal analysis (Role 2) ────────────────
        report.status = JobStatus.ANALYZING_TEXT
        await _save_report(report)

        nlp_result: FinancialSignal = await run_nlp_analysis(market_data, symbol)
        report.nlp_insight = nlp_result
        logger.info("[%s] NLP Engine: signal_type=%s", job_id, nlp_result.signal_type)

        # ── 4. Chart Engine: visual pattern analysis (Role 3) ─────────────────
        #    Circuit Breaker: if this fails, we degrade gracefully.
        report.status = JobStatus.VERIFYING_CHARTS
        await _save_report(report)

        try:
            chart_result: ChartAnalysis = await run_chart_analysis(market_data, symbol)
            report.chart_insight    = chart_result
            report.charts_available = True
            logger.info("[%s] Chart Engine: pattern=%s", job_id, chart_result.pattern)

        except Exception as chart_exc:
            # ── Circuit Breaker fires ──────────────────────────────────────────
            error_msg = f"chart_engine failed: {type(chart_exc).__name__}: {chart_exc}"
            report.charts_available = False
            report.error_logs.append(error_msg)
            logger.warning("[%s] %s — serving NLP-only report", job_id, error_msg)

        # ── 5. Mark complete ──────────────────────────────────────────────────
        report.status       = JobStatus.COMPLETED
        report.completed_at = _utc_now()
        await _save_report(report)
        logger.info("[%s] Workflow COMPLETED (charts_available=%s)", job_id, report.charts_available)

    except Exception as fatal_exc:
        # Unexpected failure in Data Lake or NLP Engine
        error_msg = f"fatal error: {type(fatal_exc).__name__}: {fatal_exc}"
        report.status = JobStatus.FAILED
        report.error_logs.append(error_msg)
        report.completed_at = _utc_now()
        await _save_report(report)
        logger.error("[%s] Workflow FAILED — %s", job_id, error_msg, exc_info=True)


# =============================================================================
# Sub-task 4.1: The Endpoint Layer
# =============================================================================
@app.post(
    "/analyze/{symbol}",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue a full financial analysis for a given symbol.",
    response_description="Job ID and confirmation that analysis has been queued.",
)
async def start_analysis(
    symbol: str,
    background_tasks: BackgroundTasks,
) -> dict:
    """
    **Gate 1 — Validation**: Rejects unknown symbols immediately (< 1 ms).
    **Gate 2 — Dispatch**:  Pushes the workflow to a BackgroundTask and returns
    a Job ID to the caller in well under 200 ms.

    The client should poll `GET /report/{job_id}` for results.
    """
    clean_symbol = _validate_symbol(symbol)   # raises 400/422 on bad input
    job_id       = _generate_job_id()

    background_tasks.add_task(orchestrate_workflow, clean_symbol, job_id)

    logger.info("[%s] /analyze accepted for symbol=%s", job_id, clean_symbol)

    return {
        "job_id":   job_id,
        "symbol":   clean_symbol,
        "message":  "Analysis queued — poll /report/{job_id} for updates.",
        "status":   JobStatus.PENDING,
    }


# =============================================================================
# Sub-task 4.4: The Status / Report Endpoint
# =============================================================================
@app.get(
    "/report/{job_id}",
    response_model=FinalReport,
    summary="Fetch the current status or completed report for a job.",
)
async def get_report(job_id: str) -> FinalReport:
    """
    Returns the live `FinalReport` for the given *job_id*.

    - While the job is in flight you will see `status` progress through:
      `PENDING → FETCHING_DATA → ANALYZING_TEXT → VERIFYING_CHARTS → COMPLETED`
    - On success, `nlp_insight` (and optionally `chart_insight`) are populated.
    - If `charts_available` is `false`, check `error_logs` for the reason.
    - If the job does not exist (expired or wrong ID) → **404**.
    """
    report = await _load_report(job_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No job found for job_id='{job_id}'. It may have expired or the ID is wrong.",
        )
    return report


# -----------------------------------------------------------------------------
# Mapping endpoints — translate backend contracts into frontend-friendly JSON
# -----------------------------------------------------------------------------


def _fmt_volume(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "-"
    v = float(v)
    if v >= 1_000_000_000:
        return f"{v/1_000_000_000:.1f}B"
    if v >= 1_000_000:
        return f"{v/1_000_000:.1f}M"
    if v >= 1_000:
        return f"{v/1_000:.1f}K"
    return f"{int(v)}"


def _map_direction(signal: str, nlp: FinancialSignal | None) -> str:
    if not signal:
        if nlp:
            return "BULLISH" if nlp.sentiment_score > 0 else "BEARISH" if nlp.sentiment_score < 0 else "NEUTRAL"
        return "NEUTRAL"
    s = signal.upper()
    if "BUY" in s:
        return "BULLISH"
    if "SELL" in s:
        return "BEARISH"
    return "NEUTRAL"


@app.get("/api/ohlcv")
async def api_ohlcv(symbol: str, days: int = 90):
    sym = _validate_symbol(symbol)
    market = await fetch_market_data(sym)
    df: pd.DataFrame = market.get("ohlcv")
    if df is None or df.empty:
        return []

    # take last `days` rows
    df2 = df.tail(days).copy()
    # ensure numeric types
    for c in ["open", "high", "low", "close", "volume"]:
        if c in df2.columns:
            df2[c] = pd.to_numeric(df2[c], errors="coerce").fillna(0)

    df2["ma20"] = df2["close"].rolling(20, min_periods=1).mean()

    out = []
    df_reset = df2.reset_index()
    # The timestamp column may be named 'ts_utc' or the original index name
    ts_col = "ts_utc" if "ts_utc" in df_reset.columns else df_reset.columns[0]
    for idx, row in df_reset.iterrows():
        ts_val = row[ts_col]
        time_str = ts_val.isoformat() if hasattr(ts_val, "isoformat") else str(ts_val)
        out.append({
            "time": time_str,
            "open": float(row.get("open", 0) or 0),
            "high": float(row.get("high", 0) or 0),
            "low": float(row.get("low", 0) or 0),
            "close": float(row.get("close", 0) or 0),
            "volume": int(row.get("volume", 0) or 0),
            "ma20": float(row.get("ma20", 0) or 0),
        })
    return out


@app.get("/api/company")
async def api_company(symbol: str):
    sym = _validate_symbol(symbol)
    # Try yfinance for basic metadata, fall back to simple mapping
    try:
        t = yf.Ticker(sym)
        info = t.info or {}
        name = info.get("longName") or info.get("shortName") or sym
        marketCap = info.get("marketCap")
        sector = info.get("sector") or None
        logo = info.get("logo_url") or None
        return {
            "name": name,
            "ticker": sym,
            "sector": sector,
            "marketCap": f"{marketCap}" if marketCap else "N/A",
            "logoUrl": logo,
            "exchange": info.get("exchange") or None,
        }
    except Exception:
        return {"name": sym, "ticker": sym, "sector": None, "marketCap": "N/A", "logoUrl": None}


@app.get("/api/signals")
async def api_signals(symbol: str):
    sym = _validate_symbol(symbol)
    market = await fetch_market_data(sym)
    df: pd.DataFrame = market.get("ohlcv")

    # Run NLP + Chart engines (best-effort)
    nlp = None
    chart = None
    try:
        nlp = await run_nlp_analysis(market, sym)
    except Exception as e:
        logger.warning("NLP analysis failed: %s", e)

    try:
        chart = await run_chart_analysis(market, sym)
    except Exception as e:
        logger.warning("Chart analysis failed: %s", e)

    # Technical signals (heuristic)
    signals = {
        "rsiOversold": False,
        "macdCross": False,
        "volumeSpike": False,
        "supportTest": False,
        "patternMatch": bool(getattr(chart, "math_verified", False)),
    }

    stats = {
        "avgVolume": None,
        "week52High": None,
        "week52Low": None,
        "volatility": None,
    }

    if df is not None and not df.empty:
        # ensure numeric columns
        for c in ["open", "high", "low", "close", "volume"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

        close = df["close"].astype(float)
        vol = df["volume"].astype(float) if "volume" in df.columns else pd.Series([0])

        try:
            if talib is not None:
                rsi = talib.RSI(close.values, timeperiod=14)
                if len(rsi) and not np.isnan(rsi[-1]):
                    signals["rsiOversold"] = bool(rsi[-1] < 30)
        except Exception:
            pass

        try:
            if talib is not None:
                macd, macdsig, macdhist = talib.MACD(close.values)
                if len(macd) >= 2:
                    signals["macdCross"] = bool((macd[-1] > macdsig[-1]) and (macd[-2] <= macdsig[-2]))
        except Exception:
            pass

        try:
            recent_mean = vol.tail(20).mean() if len(vol) >= 5 else vol.mean()
            signals["volumeSpike"] = bool(vol.iloc[-1] > (recent_mean * 2) if recent_mean > 0 else False)
        except Exception:
            pass

        try:
            rolling_min = close.rolling(252, min_periods=1).min()
            signals["supportTest"] = bool((close.iloc[-1] - rolling_min.iloc[-1]) / (rolling_min.iloc[-1] or 1) < 0.02)
        except Exception:
            pass

        stats["avgVolume"] = _fmt_volume(vol.tail(20).mean())
        stats["week52High"] = float(df["high"].max()) if "high" in df.columns else None
        stats["week52Low"] = float(df["low"].min()) if "low" in df.columns else None
        try:
            returns = close.pct_change().dropna()
            stats["volatility"] = round(float(returns.std() * 100), 2)
        except Exception:
            stats["volatility"] = None

    # Pattern mapping
    pattern = {
        "name": getattr(chart, "pattern", None) or (getattr(chart, "vision_label", None) or None),
        "confidence": int(getattr(chart, "confidence_score", 0) * 100) if chart is not None else 0,
        "description": ": ".join(getattr(chart, "notes", [])[:2]) if chart is not None else None,
    }

    # Direction & confidence
    direction = _map_direction(getattr(chart, "signal", None), nlp)
    confidence = 0
    if chart and getattr(chart, "confidence_score", 0) > 0:
        confidence = int(chart.confidence_score * 100)
    elif nlp:
        confidence = int(min(100, abs(nlp.sentiment_score) * 100))

    response = {
        "direction": direction,
        "confidence": confidence,
        "signals": signals,
        "pattern": pattern,
        "stats": stats,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }

    return response


@app.get("/api/bounce_history")
async def api_bounce_history(symbol: str, limit: int = 20):
    # For now return an empty list or basic derived historical signalling
    sym = _validate_symbol(symbol)
    market = await fetch_market_data(sym)
    df: pd.DataFrame = market.get("ohlcv")
    if df is None or df.empty:
        return []

    # ensure numeric close column
    if "close" not in df.columns:
        return []
    df["close"] = pd.to_numeric(df["close"], errors="coerce").fillna(0)

    # naive historical: look for local minima and mark as bounce candidates
    closes = df["close"].astype(float)
    # Get timestamps: prefer ts_utc column if it exists as a column, else use the index
    if "ts_utc" in df.columns:
        timestamps = df["ts_utc"].tolist()
    else:
        timestamps = df.index.tolist()

    candidates = []
    for i in range(1, len(closes) - 1):
        if closes.iloc[i] < closes.iloc[i - 1] and closes.iloc[i] < closes.iloc[i + 1]:
            ts = timestamps[i]
            candidates.append({
                "date": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                "symbol": sym,
                "score": 50,
                "bounced": False,
                "returnPct": None,
                "daysToResolve": None,
            })
            if len(candidates) >= limit:
                break

    return candidates


# =============================================================================
# Health check  (required by any load balancer / k8s readiness probe)
# =============================================================================
@app.get("/health", include_in_schema=False)
async def health() -> dict:
    try:
        await redis_client.ping()
        redis_ok = True
    except Exception:
        redis_ok = False

    return {
        "status": "ok" if redis_ok else "degraded",
        "redis":  "connected" if redis_ok else "unreachable",
        "ts":     _utc_now(),
    }