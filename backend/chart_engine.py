# backend/chart_engine.py
# Role 3: Chart Pattern Intelligence (Vision & Quant)
# Visual Auditor — bridges AI intuition with hard math via the Double-Lock Rule.

import io
import time
import logging
import functools
from typing import Optional
from dataclasses import dataclass, field
import asyncio
import os

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend — no display required
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
try:
    import talib
except ImportError:
    talib = None
try:
    import google.generativeai as genai
except Exception:
    genai = None
from minio import Minio
from minio.error import S3Error
from PIL import Image

# ─────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ChartEngine")


# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────
GEMINI_TIMEOUT_SEC = 2.0        # Flash vision call hard cap
ANALYZE_TIMEOUT_SEC = 5.0       # Entire analyze_chart() hard cap
BACKTEST_LOOKBACK = 5           # Number of historical pattern occurrences
DOUBLE_BOTTOM_TOLERANCE = 0.10  # 10 % tolerance for second low validation
MINIO_BUCKET = "chart-images"


# ─────────────────────────────────────────────
# Result dataclass
# ─────────────────────────────────────────────
@dataclass
class ChartAnalysisResult:
    symbol: str
    pattern: Optional[str]           # e.g. "Double Bottom", "Bullish Flag"
    vision_label: Optional[str]      # Raw Gemini output
    math_verified: bool              # Did TA-Lib confirm the pattern?
    confidence_score: float          # 0.0 – 1.0 from mini backtest
    signal: str                      # "BUY" | "SELL" | "HOLD" | "Inconclusive" | "Timeout"
    chart_path: Optional[str]        # MinIO object path or local path
    elapsed_sec: float
    notes: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────
# Timeout decorator (thread-safe, no UNIX signals)
# ─────────────────────────────────────────────
import concurrent.futures

def with_timeout(seconds: float):
    """Decorator: runs the wrapped function in a thread; raises TimeoutError if it exceeds `seconds`."""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(fn, *args, **kwargs)
                try:
                    return future.result(timeout=seconds)
                except concurrent.futures.TimeoutError:
                    raise TimeoutError(
                        f"{fn.__name__} exceeded {seconds}s timeout."
                    )
        return wrapper
    return decorator


# ─────────────────────────────────────────────
# Pattern → TA-Lib verifier registry
# Maps a Gemini vision label to a verification function.
# Each function returns True if the pattern is mathematically confirmed.
# ─────────────────────────────────────────────
def _verify_breakout(df: pd.DataFrame) -> bool:
    """Price must be above the rolling 20-period resistance level."""
    resistance = df["High"].rolling(20).max().iloc[-2]  # resistance before last candle
    current_price = df["Close"].iloc[-1]
    logger.debug(f"Breakout check — current: {current_price:.4f}, resistance: {resistance:.4f}")
    return current_price > resistance


def _verify_breakdown(df: pd.DataFrame) -> bool:
    """Price must be below the rolling 20-period support level."""
    support = df["Low"].rolling(20).min().iloc[-2]
    current_price = df["Close"].iloc[-1]
    logger.debug(f"Breakdown check — current: {current_price:.4f}, support: {support:.4f}")
    return current_price < support


def _verify_double_bottom(df: pd.DataFrame) -> bool:
    """
    Double-Lock rule for Double Bottom:
    Two successive local lows must be within DOUBLE_BOTTOM_TOLERANCE of each other.
    If the second low is > 10 % lower than the first, the pattern is DROPPED.
    """
    closes = df["Low"].values
    # Find local minima (simple: value < both neighbours)
    local_mins = [
        i for i in range(1, len(closes) - 1)
        if closes[i] < closes[i - 1] and closes[i] < closes[i + 1]
    ]
    if len(local_mins) < 2:
        return False
    first_low = closes[local_mins[-2]]
    second_low = closes[local_mins[-1]]
    diff = abs(second_low - first_low) / first_low
    logger.debug(f"Double Bottom — first low: {first_low:.4f}, second low: {second_low:.4f}, diff: {diff:.2%}")
    return diff <= DOUBLE_BOTTOM_TOLERANCE


def _verify_double_top(df: pd.DataFrame) -> bool:
    """Two successive highs within tolerance, and price now declining."""
    highs = df["High"].values
    local_maxs = [
        i for i in range(1, len(highs) - 1)
        if highs[i] > highs[i - 1] and highs[i] > highs[i + 1]
    ]
    if len(local_maxs) < 2:
        return False
    first_high = highs[local_maxs[-2]]
    second_high = highs[local_maxs[-1]]
    diff = abs(second_high - first_high) / first_high
    logger.debug(f"Double Top — first: {first_high:.4f}, second: {second_high:.4f}, diff: {diff:.2%}")
    return diff <= DOUBLE_BOTTOM_TOLERANCE


def _verify_head_and_shoulders(df: pd.DataFrame) -> bool:
    """
    Head must be higher than both shoulders.
    Uses rolling max over three sections of the window.
    """
    n = len(df)
    if n < 30:
        return False
    third = n // 3
    left = df["High"].iloc[:third].max()
    head = df["High"].iloc[third: 2 * third].max()
    right = df["High"].iloc[2 * third:].max()
    neckline = (df["Low"].iloc[third - 5: third].min() +
                df["Low"].iloc[2 * third - 5: 2 * third].min()) / 2
    current = df["Close"].iloc[-1]
    logger.debug(f"H&S — L:{left:.4f}, H:{head:.4f}, R:{right:.4f}, neck:{neckline:.4f}, price:{current:.4f}")
    return head > left and head > right and current < neckline


def _verify_bullish_flag(df: pd.DataFrame) -> bool:
    """Strong up-move followed by a shallow consolidation channel."""
    if len(df) < 20:
        return False
    pole = df["Close"].iloc[-20:-10]
    flag = df["Close"].iloc[-10:]
    pole_return = (pole.iloc[-1] - pole.iloc[0]) / pole.iloc[0]
    flag_return = (flag.iloc[-1] - flag.iloc[0]) / flag.iloc[0]
    logger.debug(f"Bullish Flag — pole return: {pole_return:.2%}, flag return: {flag_return:.2%}")
    return pole_return > 0.04 and -0.05 < flag_return < 0.01


def _verify_bearish_flag(df: pd.DataFrame) -> bool:
    """Strong down-move followed by a shallow up-channel."""
    if len(df) < 20:
        return False
    pole = df["Close"].iloc[-20:-10]
    flag = df["Close"].iloc[-10:]
    pole_return = (pole.iloc[-1] - pole.iloc[0]) / pole.iloc[0]
    flag_return = (flag.iloc[-1] - flag.iloc[0]) / flag.iloc[0]
    logger.debug(f"Bearish Flag — pole return: {pole_return:.2%}, flag return: {flag_return:.2%}")
    return pole_return < -0.04 and -0.01 < flag_return < 0.05


# Map: normalized Gemini label → (verifier_fn, directional_signal)
PATTERN_REGISTRY: dict[str, tuple] = {
    "bullish breakout":          (_verify_breakout,            "BUY"),
    "breakout":                  (_verify_breakout,            "BUY"),
    "bearish breakdown":         (_verify_breakdown,           "SELL"),
    "breakdown":                 (_verify_breakdown,           "SELL"),
    "double bottom":             (_verify_double_bottom,       "BUY"),
    "double top":                (_verify_double_top,          "SELL"),
    "head and shoulders":        (_verify_head_and_shoulders,  "SELL"),
    "inverse head and shoulders":(_verify_head_and_shoulders,  "BUY"),
    "bullish flag":              (_verify_bullish_flag,        "BUY"),
    "bearish flag":              (_verify_bearish_flag,        "SELL"),
}


def _normalize_pattern(raw_label: str) -> str:
    """Lowercase + strip for registry lookup."""
    return raw_label.strip().lower()


# ─────────────────────────────────────────────
# Main Engine
# ─────────────────────────────────────────────
class ChartEngine:
    """
    Role 3: Chart Pattern Intelligence
    ───────────────────────────────────
    Sub-task 3.1  _render_chart()         → Clean PNG → MinIO
    Sub-task 3.2  _get_visual_pattern()   → Gemini 1.5 Flash (2 s timeout)
    Sub-task 3.3  _verify_pattern()       → TA-Lib Double-Lock validation
    Sub-task 3.4  _backtest_pattern()     → Last-5 mini backtest
    Public API    analyze_chart()         → ChartAnalysisResult (5 s total cap)
    """

    def __init__(
        self,
        gemini_api_key: str,
        minio_endpoint: str = "localhost:9000",
        minio_access_key: str = "minioadmin",
        minio_secret_key: str = "minioadmin",
        minio_secure: bool = False,
    ):
        # ── Gemini (optional) ─────────────────────
        if genai is not None and gemini_api_key:
            try:
                genai.configure(api_key=gemini_api_key)
                self._flash = genai.GenerativeModel("gemini-1.5-flash")
            except Exception as e:
                logger.warning(f"Gemini client init failed: {e}. Falling back to Pure Math mode.")
                self._flash = None
        else:
            self._flash = None

        # ── MinIO ───────────────────────────────
        self._minio = Minio(
            minio_endpoint,
            access_key=minio_access_key,
            secret_key=minio_secret_key,
            secure=minio_secure,
        )
        self._ensure_bucket()

        logger.info("ChartEngine initialized.")

    # ─────────────────────────────────────────
    # Bucket setup
    # ─────────────────────────────────────────
    def _ensure_bucket(self):
        try:
            if not self._minio.bucket_exists(MINIO_BUCKET):
                self._minio.make_bucket(MINIO_BUCKET)
                logger.info(f"Created MinIO bucket '{MINIO_BUCKET}'.")
            self._minio_available = True
        except Exception as e:
            logger.warning(f"MinIO unavailable — chart storage disabled: {e}")
            self._minio_available = False

    # ─────────────────────────────────────────
    # Sub-task 3.1 — Renderer
    # ─────────────────────────────────────────
    def _render_chart(self, df: pd.DataFrame, symbol: str) -> str:
        """
        Generates a clean, noise-free candlestick PNG.
        No moving averages. No volume. Just price action.
        Saves to MinIO and returns the object path.
        """
        fig, ax = plt.subplots(figsize=(12, 6), dpi=150)
        fig.patch.set_facecolor("#0d0d0d")
        ax.set_facecolor("#0d0d0d")

        for _, row in df.iterrows():
            color = "#00e676" if row["Close"] >= row["Open"] else "#ff1744"
            # Candle body
            body_low = min(row["Open"], row["Close"])
            body_height = abs(row["Close"] - row["Open"])
            ax.add_patch(FancyBboxPatch(
                (row.name - 0.4, body_low), 0.8, max(body_height, df["Close"].mean() * 0.001),
                boxstyle="square,pad=0", linewidth=0, facecolor=color, alpha=0.9
            ))
            # Wicks
            ax.plot([row.name, row.name], [row["Low"], row["High"]],
                    color=color, linewidth=0.8, alpha=0.7)

        ax.set_xlim(df.index[0] - 1, df.index[-1] + 1)
        ax.set_ylim(df["Low"].min() * 0.995, df["High"].max() * 1.005)
        ax.tick_params(colors="#aaaaaa", labelsize=8)
        for spine in ax.spines.values():
            spine.set_edgecolor("#333333")
        ax.set_title(f"{symbol} — Price Action", color="#eeeeee", fontsize=11, pad=10)
        ax.grid(color="#1e1e1e", linewidth=0.5, linestyle="--")

        # Save to bytes buffer
        buf = io.BytesIO()
        plt.savefig(buf, format="png", bbox_inches="tight", facecolor=fig.get_facecolor())
        buf.seek(0)
        plt.close(fig)

        # Upload to MinIO (if available)
        object_name = f"{symbol}_{int(time.time())}.png"
        buf_size = buf.getbuffer().nbytes
        if getattr(self, "_minio_available", False):
            try:
                self._minio.put_object(
                    MINIO_BUCKET, object_name, buf, buf_size, content_type="image/png"
                )
                path = f"{MINIO_BUCKET}/{object_name}"
                logger.info(f"Chart saved to MinIO: {path}")
            except Exception as e:
                logger.warning(f"MinIO upload failed ({e}). Using in-memory buffer.")
                path = f"memory://{symbol}_{int(time.time())}.png"
        else:
            path = f"memory://{symbol}_{int(time.time())}.png"

        # Reset buffer for Gemini consumption
        buf.seek(0)
        self._last_chart_buf = buf   # stash for vision call

        return path

    # ─────────────────────────────────────────
    # Sub-task 3.2 — Vision Call (Gemini 1.5 Flash)
    # ─────────────────────────────────────────
    def _get_visual_pattern(self) -> Optional[str]:
        """
        Sends the rendered chart to Gemini 1.5 Flash.
        Hard timeout: 2 seconds.
        Falls back to None (→ Pure Math mode) on timeout or error.
        """
        prompt = (
            "You are a professional technical analyst. "
            "Examine this candlestick chart and identify the single most prominent "
            "chart pattern visible. "
            "Reply with ONLY the pattern name — nothing else. "
            "Valid patterns: Bullish Breakout, Bearish Breakdown, Double Bottom, "
            "Double Top, Head and Shoulders, Inverse Head and Shoulders, "
            "Bullish Flag, Bearish Flag, Symmetrical Triangle, Ascending Triangle, "
            "Descending Triangle, Cup and Handle, Rising Wedge, Falling Wedge, "
            "Inconclusive."
        )

        # If Gemini client isn't configured or available, skip vision step.
        if not getattr(self, "_flash", None):
            logger.debug("Gemini client unavailable — skipping visual pattern detection.")
            return None

        @with_timeout(GEMINI_TIMEOUT_SEC)
        def _call_flash() -> str:
            img_bytes = self._last_chart_buf.read()
            image_part = {"mime_type": "image/png", "data": img_bytes}
            response = self._flash.generate_content([prompt, image_part])
            return response.text.strip()

        try:
            label = _call_flash()
            logger.info(f"Gemini vision label: '{label}'")
            return label
        except TimeoutError:
            logger.warning("Gemini 1.5 Flash timed out (>2s). Switching to Pure Math mode.")
            return None
        except Exception as e:
            logger.error(f"Gemini vision error: {e}")
            return None

    # ─────────────────────────────────────────
    # Sub-task 3.3 — Double-Lock Validator (TA-Lib)
    # ─────────────────────────────────────────
    def _verify_pattern(
        self, vision_label: str, df: pd.DataFrame
    ) -> tuple[bool, str, str]:
        """
        Cross-references the AI visual label with TA-Lib math.
        Returns:
          (math_verified: bool, canonical_pattern: str, directional_signal: str)
        """
        key = _normalize_pattern(vision_label)
        if key not in PATTERN_REGISTRY:
            logger.info(f"Pattern '{vision_label}' not in registry — marking Inconclusive.")
            return False, vision_label, "Inconclusive"

        verifier_fn, direction = PATTERN_REGISTRY[key]
        try:
            verified = verifier_fn(df)
        except Exception as e:
            logger.error(f"TA-Lib verifier error for '{vision_label}': {e}")
            verified = False

        if not verified:
            logger.warning(
                f"Double-Lock FAILED for '{vision_label}'. "
                f"Pattern DROPPED — signal set to Inconclusive."
            )
        else:
            logger.info(f"Double-Lock PASSED for '{vision_label}'. Signal: {direction}")

        return verified, vision_label, direction if verified else "Inconclusive"

    # ─────────────────────────────────────────
    # Sub-task 3.4 — Mini Backtest
    # ─────────────────────────────────────────
    def _backtest_pattern(self, pattern: str, df: pd.DataFrame) -> float:
        """
        Scans historical data for the last BACKTEST_LOOKBACK occurrences of
        the same pattern family and returns a win-rate confidence score (0.0–1.0).
        Uses TA-Lib CDL functions where available; falls back to rolling-window heuristics.
        Speed constraint: only last 5 occurrences, no full simulation.
        """
        key = _normalize_pattern(pattern)
        close = df["Close"].values.astype(float)
        open_ = df["Open"].values.astype(float)
        high = df["High"].values.astype(float)
        low = df["Low"].values.astype(float)

        # Map pattern → TA-Lib CDL function (best-effort)
        CDL_MAP = {
            "double bottom":   lambda: talib.CDLMORNINGDOJI(open_, high, low, close),
            "double top":      lambda: talib.CDLEVENINGDOJI(open_, high, low, close),
            "bullish flag":    lambda: talib.CDL3WHITESOLDIERS(open_, high, low, close),
            "bearish flag":    lambda: talib.CDL3BLACKCROWS(open_, high, low, close),
            "head and shoulders": lambda: talib.CDLEVENINGSTAR(open_, high, low, close, penetration=0),
            "bullish breakout":lambda: (close > talib.MAX(close, 20)).astype(int) * 100,
            "bearish breakdown": lambda: (close < talib.MIN(close, 20)).astype(int) * -100,
        }

        signal_series = None
        if key in CDL_MAP:
            try:
                signal_series = CDL_MAP[key]()
            except Exception as e:
                logger.warning(f"TA-Lib CDL call failed for '{pattern}': {e}")

        if signal_series is None:
            # Generic heuristic: momentum confirmation
            if talib is not None:
                try:
                    roc = talib.ROC(close, timeperiod=5)
                    is_bullish = "buy" in key or "bottom" in key or "breakout" in key or "flag" in key
                    signal_series = np.where(roc > 1.0 if is_bullish else roc < -1.0, 100, 0)
                except Exception:
                    pass
            if signal_series is None:
                logger.info(f"TA-Lib unavailable for backtest of '{pattern}'. Confidence: 0.50.")
                return 0.50

        # Find signal occurrences (non-zero)
        occurrences = np.where(signal_series != 0)[0]
        if len(occurrences) == 0:
            logger.info(f"No historical occurrences found for '{pattern}'. Confidence: 0.50 (neutral).")
            return 0.50

        # Take last N occurrences
        sample = occurrences[-BACKTEST_LOOKBACK:]
        wins = 0
        for idx in sample:
            # Define "win": price is higher (for bullish) or lower (for bearish) 5 bars later
            look_ahead = min(idx + 5, len(close) - 1)
            future_return = (close[look_ahead] - close[idx]) / close[idx]
            is_bullish_signal = signal_series[idx] > 0
            if is_bullish_signal and future_return > 0:
                wins += 1
            elif not is_bullish_signal and future_return < 0:
                wins += 1

        confidence = wins / len(sample)
        logger.info(
            f"Mini backtest '{pattern}': {wins}/{len(sample)} wins → "
            f"confidence {confidence:.0%}"
        )
        return round(confidence, 4)

    # ─────────────────────────────────────────
    # Public API — analyze_chart()
    # ─────────────────────────────────────────
    @with_timeout(ANALYZE_TIMEOUT_SEC)
    def analyze_chart(self, symbol: str, df: pd.DataFrame) -> ChartAnalysisResult:
        """
        Full pipeline with 5-second hard cap:
          1. Render clean chart → MinIO
          2. Gemini 1.5 Flash vision (2 s inner timeout)
          3. Double-Lock TA-Lib validation
          4. Mini backtest → confidence score
        Returns ChartAnalysisResult. On timeout, the decorator raises TimeoutError
        which the Gateway should catch and return a Timeout result.
        """
        t0 = time.perf_counter()
        notes: list[str] = []

        # ── Validate input ───────────────────
        required_cols = {"Open", "High", "Low", "Close"}
        if not required_cols.issubset(df.columns):
            raise ValueError(f"DataFrame must contain columns: {required_cols}")
        if len(df) < 30:
            raise ValueError("Need at least 30 candles for reliable pattern detection.")

        # Reset integer index for rendering
        df = df.reset_index(drop=True)

        # ── 3.1 Render ───────────────────────
        chart_path = self._render_chart(df, symbol)

        # ── 3.2 Gemini vision ────────────────
        vision_label = self._get_visual_pattern()
        pure_math_mode = vision_label is None

        if pure_math_mode:
            notes.append("Gemini timed out — running in Pure Math mode.")
            # In Pure Math mode: use TA-Lib to detect any strong candle pattern
            vision_label = self._pure_math_pattern(df)
            notes.append(f"Pure Math detected: {vision_label}")

        # ── 3.3 Double-Lock validation ───────
        math_verified, canonical_pattern, signal = self._verify_pattern(vision_label, df)

        if not math_verified and not pure_math_mode:
            notes.append(
                f"Double-Lock FAILED: Gemini said '{vision_label}' but TA-Lib "
                f"did not confirm. Signal dropped."
            )

        # ── 3.4 Backtest (only if pattern verified) ──
        confidence = 0.0
        if math_verified and signal not in ("Inconclusive", "Timeout"):
            confidence = self._backtest_pattern(canonical_pattern, df)
        else:
            confidence = 0.0
            notes.append("Backtest skipped — pattern not verified.")

        elapsed = round(time.perf_counter() - t0, 3)
        logger.info(
            f"[{symbol}] analyze_chart complete in {elapsed}s | "
            f"pattern={canonical_pattern} | verified={math_verified} | "
            f"signal={signal} | confidence={confidence:.0%}"
        )

        return ChartAnalysisResult(
            symbol=symbol,
            pattern=canonical_pattern,
            vision_label=vision_label,
            math_verified=math_verified,
            confidence_score=confidence,
            signal=signal,
            chart_path=chart_path,
            elapsed_sec=elapsed,
            notes=notes,
        )

    # ─────────────────────────────────────────
    # Pure Math fallback (no Gemini)
    # ─────────────────────────────────────────
    def _pure_math_pattern(self, df: pd.DataFrame) -> str:
        """
        When Gemini is unavailable, derive a pattern label purely from TA-Lib.
        Returns the strongest signal found, or 'Inconclusive'.
        """
        if talib is None:
            logger.info("TA-Lib not installed — returning Inconclusive.")
            return "Inconclusive"

        o = df["Open"].values.astype(float)
        h = df["High"].values.astype(float)
        l = df["Low"].values.astype(float)
        c = df["Close"].values.astype(float)

        try:
            checks = {
                "Bullish Breakout":   (talib.MAX(c, 20)[-1] == c[-1]),
                "Bearish Breakdown":  (talib.MIN(c, 20)[-1] == c[-1]),
                "Double Bottom":      (talib.CDLMORNINGDOJI(o, h, l, c)[-1] != 0),
                "Double Top":         (talib.CDLEVENINGDOJI(o, h, l, c)[-1] != 0),
                "Bullish Flag":       (talib.CDL3WHITESOLDIERS(o, h, l, c)[-1] != 0),
                "Bearish Flag":       (talib.CDL3BLACKCROWS(o, h, l, c)[-1] != 0),
            }
            for pattern_name, condition in checks.items():
                if condition:
                    return pattern_name
        except Exception as e:
            logger.warning(f"TA-Lib pure math detection failed: {e}")
        return "Inconclusive"


# ─────────────────────────────────────────────
# Gateway-level wrapper (handles TimeoutError)
# ─────────────────────────────────────────────
def safe_analyze(engine: ChartEngine, symbol: str, df: pd.DataFrame) -> ChartAnalysisResult:
    """
    Drop-in wrapper for the Gateway/Router to call.
    Catches the 5-second TimeoutError and returns a safe Timeout result
    instead of propagating an exception.
    """
    try:
        return engine.analyze_chart(symbol, df)
    except TimeoutError as e:
        logger.error(f"[{symbol}] analyze_chart TIMEOUT: {e}")
        return ChartAnalysisResult(
            symbol=symbol,
            pattern=None,
            vision_label=None,
            math_verified=False,
            confidence_score=0.0,
            signal="Timeout",
            chart_path=None,
            elapsed_sec=ANALYZE_TIMEOUT_SEC,
            notes=[f"Pipeline exceeded {ANALYZE_TIMEOUT_SEC}s. Gateway received Timeout."],
        )
    except Exception as e:
        logger.error(f"[{symbol}] Unexpected error: {e}", exc_info=True)
        return ChartAnalysisResult(
            symbol=symbol,
            pattern=None,
            vision_label=None,
            math_verified=False,
            confidence_score=0.0,
            signal="Inconclusive",
            chart_path=None,
            elapsed_sec=0.0,
            notes=[f"Unexpected error: {str(e)}"],
        )


# Backwards-compat aliases and async adapter expected by the orchestrator
# Expose `ChartAnalysis` type and an async `run_chart_analysis` helper so
# `main.py` can import these symbols without refactoring.
ChartAnalysis = ChartAnalysisResult


async def run_chart_analysis(market_data: dict, symbol: str) -> ChartAnalysis:
    """
    Async adapter used by the orchestrator.
    - Expects `market_data` as returned by `DataLakeEngine.query_cached_data`.
    - Converts snake_case OHLCV columns to the TitleCase names expected by
      `ChartEngine.analyze_chart` then runs the synchronous analysis on a
      background thread (honouring the chart engine's internal timeouts).
    """
    df = market_data.get("ohlcv")
    if df is None:
        raise ValueError("market_data must include an 'ohlcv' DataFrame")

    # Column mapping: snake_case (data_lake) → TitleCase (chart engine)
    col_map = {"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}
    df2 = df.copy()
    df2 = df2.rename(columns={k: v for k, v in col_map.items() if k in df2.columns})

    gemini_api_key = os.getenv("GEMINI_API_KEY", "")
    minio_endpoint = os.getenv("MINIO_ENDPOINT", "localhost:9000")
    minio_access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    minio_secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    minio_secure = os.getenv("MINIO_SECURE", "false").lower() in ("1", "true", "yes")

    engine = ChartEngine(
        gemini_api_key=gemini_api_key,
        minio_endpoint=minio_endpoint,
        minio_access_key=minio_access_key,
        minio_secret_key=minio_secret_key,
        minio_secure=minio_secure,
    )

    # Use safe_analyze wrapper in a thread so timeouts return safe results
    return await asyncio.to_thread(safe_analyze, engine, symbol, df2)


# ─────────────────────────────────────────────
# Quick smoke-test (remove in production)
# ─────────────────────────────────────────────
if __name__ == "__main__":
    import os

    # Synthetic OHLCV data — replace with Role 1 feed
    np.random.seed(42)
    n = 60
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    df_test = pd.DataFrame({
        "Open":  close - np.abs(np.random.randn(n) * 0.3),
        "High":  close + np.abs(np.random.randn(n) * 0.6),
        "Low":   close - np.abs(np.random.randn(n) * 0.6),
        "Close": close,
        "Volume": np.random.randint(1_000, 10_000, n),
    })

    engine = ChartEngine(
        gemini_api_key=os.getenv("GEMINI_API_KEY", "YOUR_KEY_HERE"),
    )
    result = safe_analyze(engine, "BTC/USDT", df_test)

    print("\n── ChartAnalysisResult ──────────────────")
    print(f"  Symbol:     {result.symbol}")
    print(f"  Pattern:    {result.pattern}")
    print(f"  Vision:     {result.vision_label}")
    print(f"  Math OK:    {result.math_verified}")
    print(f"  Confidence: {result.confidence_score:.0%}")
    print(f"  Signal:     {result.signal}")
    print(f"  Elapsed:    {result.elapsed_sec}s")
    print(f"  Chart:      {result.chart_path}")
    if result.notes:
        print("  Notes:")
        for n_ in result.notes:
            print(f"    • {n_}")