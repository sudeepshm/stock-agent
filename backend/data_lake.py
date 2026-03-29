# backend/data_lake.py
"""
DataLakeEngine — Role 1: Data Ingestion
========================================
Responsibilities:
  1.1  Fetcher        — Network layer (yfinance / NSE announcements)
  1.2  Normalizer     — Time-series math layer (UTC / IST standardisation)
  1.3  Persistence    — Storage layer (Postgres for rows, MinIO for PDFs)
  1.4  Query Interface— Internal API exclusively for Roles 2 and 3

Design constraints:
  - No "naive" timestamps anywhere in the pipeline.
  - PDF de-duplication via SHA-256 hash; never store the same file twice.
  - query_cached_data() is FORBIDDEN from calling the internet.
  - Network failures degrade gracefully: return Status: Cached instead of crash.
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import requests
import yfinance as yf
from minio import Minio
from minio.error import S3Error
from requests.exceptions import RequestException
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from zoneinfo import ZoneInfo  # Python 3.9+; use pytz if < 3.9
import asyncio

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
IST = ZoneInfo("Asia/Kolkata")
UTC = timezone.utc

NSE_ANNOUNCEMENT_BASE = "https://www.nseindia.com/api/corp-announcements"
BSE_ANNOUNCEMENT_BASE = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"

DEFAULT_OHLCV_COLUMNS = {
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Volume": "volume",
    "Adj Close": "adj_close",
}

# ---------------------------------------------------------------------------
# SQLAlchemy ORM models
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


class OHLCVRecord(Base):
    """One row = one candle for one symbol."""

    __tablename__ = "ohlcv"
    __table_args__ = (UniqueConstraint("symbol", "ts_utc", name="uq_symbol_ts"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(32), nullable=False, index=True)
    ts_utc = Column(DateTime(timezone=True), nullable=False, index=True)
    ts_ist = Column(DateTime(timezone=True), nullable=False)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    adj_close = Column(Float)
    volume = Column(Float)
    source = Column(String(64), default="yfinance")


class DocumentRecord(Base):
    """Metadata for every PDF stored in MinIO."""

    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("sha256_hash", name="uq_doc_hash"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(32), nullable=False, index=True)
    sha256_hash = Column(String(64), nullable=False)
    bucket_name = Column(String(128), nullable=False)
    object_key = Column(String(512), nullable=False)
    original_filename = Column(String(512))
    doc_type = Column(String(64), default="transcript")
    uploaded_at_utc = Column(DateTime(timezone=True), nullable=False)
    source_url = Column(Text)


# ---------------------------------------------------------------------------
# DataLakeEngine
# ---------------------------------------------------------------------------


class DataLakeEngine:
    """
    The central data-lake controller.

    Parameters
    ----------
    db_url : str
        SQLAlchemy connection string, e.g.
        "postgresql+psycopg2://user:pass@localhost:5432/datalake"
    minio_endpoint : str
        MinIO host:port, e.g. "localhost:9000"
    minio_access_key : str
    minio_secret_key : str
    minio_secure : bool
        Use TLS? Default False for local dev.
    """

    def __init__(
        self,
        db_url: str = os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg2://postgres:postgres@localhost:5432/datalake",
        ),
        minio_endpoint: str = os.getenv("MINIO_ENDPOINT", "localhost:9000"),
        minio_access_key: str = os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
        minio_secret_key: str = os.getenv("MINIO_SECRET_KEY", "minioadmin"),
        minio_secure: bool = False,
    ) -> None:
        # ── Postgres ──────────────────────────────────────────────────────
        self._engine = create_engine(db_url, pool_pre_ping=True, future=True)
        self._Session: sessionmaker[Session] = sessionmaker(
            bind=self._engine, expire_on_commit=False
        )
        Base.metadata.create_all(self._engine)  # idempotent DDL bootstrap
        logger.info("Postgres connected: %s", db_url.split("@")[-1])

        # ── MinIO ─────────────────────────────────────────────────────────
        self._minio: Minio = Minio(
            minio_endpoint,
            access_key=minio_access_key,
            secret_key=minio_secret_key,
            secure=minio_secure,
        )
        logger.info("MinIO client initialised: %s", minio_endpoint)

    # =========================================================================
    # Sub-task 1.1 — Fetcher (Network Layer)
    # =========================================================================

    def sync_external_data(self, symbol: str) -> dict:
        """
        Entry-point called by a scheduler / CLI to refresh data for *symbol*.

        Fetches OHLCV from yfinance and corporate announcements (PDFs)
        from NSE/BSE. On any network error the method returns gracefully
        with a ``status: "cached"`` payload so callers can continue.

        Parameters
        ----------
        symbol : str
            Exchange ticker, e.g. "RELIANCE.NS", "TCS.BO"

        Returns
        -------
        dict
            {
                "status":  "synced" | "cached",
                "symbol":  str,
                "rows_upserted": int,
                "docs_stored": int,
                "error": str | None
            }
        """
        result = {
            "status": "cached",
            "symbol": symbol,
            "rows_upserted": 0,
            "docs_stored": 0,
            "error": None,
        }

        # ── OHLCV from yfinance ───────────────────────────────────────────
        try:
            raw_df = self._fetch_ohlcv(symbol)
            if raw_df is not None and not raw_df.empty:
                clean_df = self._apply_standard_format(raw_df)
                rows = self.save_to_storage(clean_df, data_type="price", symbol=symbol)
                result["rows_upserted"] = rows
                result["status"] = "synced"
        except RequestException as exc:
            logger.warning("[%s] OHLCV fetch failed — network error: %s", symbol, exc)
            result["error"] = str(exc)

        # ── Announcements / transcripts from NSE ─────────────────────────
        try:
            pdf_paths = self._fetch_announcements(symbol)
            for path in pdf_paths:
                bucket = "transcripts"
                stored = self.save_to_storage(
                    path, data_type="document", symbol=symbol, bucket_name=bucket
                )
                result["docs_stored"] += stored
            if pdf_paths:
                result["status"] = "synced"
        except RequestException as exc:
            logger.warning(
                "[%s] Announcement fetch failed — network error: %s", symbol, exc
            )
            if not result["error"]:
                result["error"] = str(exc)

        return result

    def _fetch_ohlcv(
        self, symbol: str, period: str = "1y", interval: str = "1d"
    ) -> Optional[pd.DataFrame]:
        """Download OHLCV from yfinance. Raises RequestException on failure."""
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval=interval, auto_adjust=False)
            if df.empty:
                logger.info("[%s] yfinance returned empty DataFrame.", symbol)
                return None
            logger.info("[%s] Fetched %d rows from yfinance.", symbol, len(df))
            return df
        except Exception as exc:
            raise RequestException(f"yfinance error for {symbol}: {exc}") from exc

    def _fetch_announcements(self, symbol: str) -> list[Path]:
        """
        Download corporate announcement PDFs from NSE.

        Returns a list of local temporary file paths.
        Raises RequestException on network failure.
        """
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0"})

        # Establish NSE session cookie
        try:
            session.get("https://www.nseindia.com", timeout=10)
        except RequestException as exc:
            raise RequestException(f"NSE cookie init failed: {exc}") from exc

        params = {
            "index": "equities",
            "symbol": symbol.replace(".NS", "").upper(),
        }
        resp = session.get(NSE_ANNOUNCEMENT_BASE, params=params, timeout=15)
        resp.raise_for_status()

        announcements = resp.json() if resp.content else []
        saved_paths: list[Path] = []

        for ann in announcements[:5]:  # cap at 5 per sync cycle
            pdf_url = ann.get("attchmntFile")
            if not pdf_url:
                continue
            try:
                pdf_resp = session.get(pdf_url, timeout=20)
                pdf_resp.raise_for_status()
            except RequestException:
                continue

            tmp_path = Path(f"/tmp/{uuid.uuid4().hex}.pdf")
            tmp_path.write_bytes(pdf_resp.content)
            saved_paths.append(tmp_path)
            logger.info("[%s] Downloaded announcement PDF → %s", symbol, tmp_path)

        return saved_paths

    # =========================================================================
    # Sub-task 1.2 — Time-Series Normalizer (Math Layer)
    # =========================================================================

    def _apply_standard_format(self, raw_df: pd.DataFrame) -> pd.DataFrame:
        """
        Internal helper: standardises column names and timestamps.

        Rules
        -----
        - Rename yfinance columns (Open / High / Low …) to snake_case.
        - Convert the DatetimeIndex to timezone-aware UTC.
        - Derive an IST column alongside.
        - Drop rows where OHLCV is entirely NaN.
        - Reject any "naive" (tz-unaware) timestamps — raise ValueError.

        Parameters
        ----------
        raw_df : pd.DataFrame
            Raw yfinance output with a DatetimeIndex.

        Returns
        -------
        pd.DataFrame
            Cleaned DataFrame with columns:
            ts_utc | ts_ist | open | high | low | close | adj_close | volume
        """
        df = raw_df.copy()

        # ── Rename columns ────────────────────────────────────────────────
        df.rename(columns=DEFAULT_OHLCV_COLUMNS, inplace=True)
        keep = [c for c in DEFAULT_OHLCV_COLUMNS.values() if c in df.columns]
        df = df[keep]

        # ── Timestamp normalisation ───────────────────────────────────────
        idx = df.index  # DatetimeIndex from yfinance
        if idx.tz is None:
            # Naive — assume UTC (yfinance date-only indices are midnight UTC)
            idx = idx.tz_localize("UTC")
        else:
            idx = idx.tz_convert("UTC")

        df.index = idx
        df.index.name = "ts_utc"
        df["ts_utc"] = df.index
        df["ts_ist"] = df["ts_utc"].dt.tz_convert(IST)

        # Enforce no naive timestamps remain
        if df["ts_utc"].dt.tz is None or df["ts_ist"].dt.tz is None:
            raise ValueError(
                "Naive timestamps detected after normalisation — aborting."
            )

        # ── Drop fully-null OHLCV rows ────────────────────────────────────
        ohlcv_cols = [
            c for c in ["open", "high", "low", "close", "volume"] if c in df.columns
        ]
        before = len(df)
        df.dropna(subset=ohlcv_cols, how="all", inplace=True)
        dropped = before - len(df)
        if dropped:
            logger.info("Dropped %d fully-null rows during normalisation.", dropped)

        df.reset_index(drop=True, inplace=True)
        return df

    # =========================================================================
    # Sub-task 1.3 — Persistence (Storage Layer)
    # =========================================================================

    def save_to_storage(
        self,
        data,
        data_type: str = "price",
        symbol: str = "",
        bucket_name: str = "transcripts",
    ) -> int:
        """
        Route data to the correct backend.

        Parameters
        ----------
        data :
            pd.DataFrame  → Postgres (data_type="price")
            pathlib.Path  → MinIO    (data_type="document")
        data_type : str
            "price" or "document"
        symbol : str
            Ticker symbol for metadata / indexing.
        bucket_name : str
            MinIO bucket (used only for documents).

        Returns
        -------
        int
            Number of rows upserted (price) or 1/0 if doc was stored/skipped.
        """
        if data_type == "price":
            if not isinstance(data, pd.DataFrame):
                raise TypeError("Expected pd.DataFrame for data_type='price'")
            return self._persist_ohlcv(data, symbol)

        elif data_type == "document":
            if not isinstance(data, Path):
                raise TypeError("Expected pathlib.Path for data_type='document'")
            return self._store_document(data, bucket_name, symbol)

        else:
            raise ValueError(f"Unknown data_type: {data_type!r}")

    def _persist_ohlcv(self, df: pd.DataFrame, symbol: str) -> int:
        """Upsert OHLCV rows into Postgres. Returns count of inserted rows."""
        records_inserted = 0

        with self._Session() as session:
            for _, row in df.iterrows():
                existing = (
                    session.query(OHLCVRecord)
                    .filter_by(symbol=symbol, ts_utc=row["ts_utc"])
                    .first()
                )
                if existing:
                    # Update price fields in-place
                    for col in ["open", "high", "low", "close", "adj_close", "volume"]:
                        if col in row:
                            setattr(existing, col, row[col])
                else:
                    record = OHLCVRecord(
                        symbol=symbol,
                        ts_utc=row["ts_utc"],
                        ts_ist=row["ts_ist"],
                        open=row.get("open"),
                        high=row.get("high"),
                        low=row.get("low"),
                        close=row.get("close"),
                        adj_close=row.get("adj_close"),
                        volume=row.get("volume"),
                        source="yfinance",
                    )
                    session.add(record)
                    records_inserted += 1

            session.commit()

        logger.info(
            "[%s] Upserted %d new OHLCV rows into Postgres.", symbol, records_inserted
        )
        return records_inserted

    def _store_document(
        self, file_path: Path, bucket_name: str, symbol: str
    ) -> int:
        """
        Store a PDF in MinIO with SHA-256 de-duplication.

        Algorithm
        ---------
        1. Compute SHA-256 hash of file bytes.
        2. Check DocumentRecord table — if hash already exists, skip.
        3. Ensure bucket exists; upload with a hash-based object key.
        4. Record metadata in DocumentRecord table.

        Returns 1 if stored, 0 if duplicate skipped.
        """
        file_bytes = file_path.read_bytes()
        sha256 = hashlib.sha256(file_bytes).hexdigest()

        with self._Session() as session:
            duplicate = (
                session.query(DocumentRecord).filter_by(sha256_hash=sha256).first()
            )
            if duplicate:
                logger.info(
                    "Duplicate PDF skipped (hash=%s…, existing key=%s/%s).",
                    sha256[:12],
                    duplicate.bucket_name,
                    duplicate.object_key,
                )
                return 0

            # Ensure MinIO bucket exists
            try:
                if not self._minio.bucket_exists(bucket_name):
                    self._minio.make_bucket(bucket_name)
            except S3Error as exc:
                logger.error("MinIO bucket operation failed: %s", exc)
                raise

            object_key = f"{symbol}/{sha256}.pdf"
            self._minio.put_object(
                bucket_name,
                object_key,
                data=io.BytesIO(file_bytes),
                length=len(file_bytes),
                content_type="application/pdf",
            )
            logger.info("Stored PDF → minio://%s/%s", bucket_name, object_key)

            doc_record = DocumentRecord(
                symbol=symbol,
                sha256_hash=sha256,
                bucket_name=bucket_name,
                object_key=object_key,
                original_filename=file_path.name,
                doc_type="transcript",
                uploaded_at_utc=datetime.now(tz=UTC),
            )
            session.add(doc_record)
            session.commit()

        return 1

    # =========================================================================
    # Sub-task 1.4 — Query Interface (Internal API)
    # =========================================================================

    def query_cached_data(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> dict:
        """
        THE ONLY FUNCTION Roles 2 and 3 are allowed to call.

        Reads exclusively from local Postgres — ZERO network calls allowed.

        Parameters
        ----------
        symbol : str
            Ticker symbol.
        start_date : datetime, optional
            Lower bound (inclusive). Should be tz-aware; naive values are
            coerced to UTC automatically.
        end_date : datetime, optional
            Upper bound (inclusive). Same tz rule.

        Returns
        -------
        dict
            {
                "symbol":      str,
                "ohlcv":       pd.DataFrame,   # indexed by ts_utc
                "documents":   list[dict],      # metadata dicts (no binary data)
                "queried_at":  datetime,        # UTC
                "rows":        int,
                "docs":        int,
            }
        """
        # Defensive: convert naive datetimes to UTC
        start_date = self._ensure_utc(start_date)
        end_date = self._ensure_utc(end_date)

        with self._Session() as session:
            ohlcv_df = self._load_ohlcv(session, symbol, start_date, end_date)
            doc_list = self._load_documents(session, symbol)

        return {
            "symbol": symbol,
            "ohlcv": ohlcv_df,
            "documents": doc_list,
            "queried_at": datetime.now(tz=UTC),
            "rows": len(ohlcv_df),
            "docs": len(doc_list),
        }

    def _load_ohlcv(
        self,
        session: Session,
        symbol: str,
        start_date: Optional[datetime],
        end_date: Optional[datetime],
    ) -> pd.DataFrame:
        """Fetch OHLCV rows from Postgres and return as a DataFrame."""
        query = session.query(OHLCVRecord).filter(OHLCVRecord.symbol == symbol)

        if start_date:
            query = query.filter(OHLCVRecord.ts_utc >= start_date)
        if end_date:
            query = query.filter(OHLCVRecord.ts_utc <= end_date)

        records = query.order_by(OHLCVRecord.ts_utc).all()

        if not records:
            logger.info("[%s] No cached OHLCV data found.", symbol)
            return pd.DataFrame(
                columns=[
                    "ts_utc", "ts_ist", "open", "high",
                    "low", "close", "adj_close", "volume",
                ]
            )

        rows = [
            {
                "ts_utc": r.ts_utc,
                "ts_ist": r.ts_ist,
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "adj_close": r.adj_close,
                "volume": r.volume,
            }
            for r in records
        ]
        df = pd.DataFrame(rows).set_index("ts_utc")
        return df

    def _load_documents(self, session: Session, symbol: str) -> list[dict]:
        """Return document metadata list for symbol (no binary payloads)."""
        docs = session.query(DocumentRecord).filter_by(symbol=symbol).all()
        return [
            {
                "id": d.id,
                "symbol": d.symbol,
                "sha256_hash": d.sha256_hash,
                "bucket_name": d.bucket_name,
                "object_key": d.object_key,
                "original_filename": d.original_filename,
                "doc_type": d.doc_type,
                "uploaded_at_utc": d.uploaded_at_utc,
            }
            for d in docs
        ]

    # =========================================================================
    # Utility helpers
    # =========================================================================

    @staticmethod
    def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
        """Convert naive datetimes to UTC. Pass None through unchanged."""
        if dt is None:
            return None
        if dt.tzinfo is None:
            logger.debug("Naive datetime detected — assuming UTC: %s", dt)
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)

    def health_check(self) -> dict:
        """
        Ping Postgres and MinIO.

        Returns a dict with 'db' and 'minio' status strings.
        Useful for Docker / Kubernetes liveness probes.
        """
        status = {"db": "unknown", "minio": "unknown"}

        try:
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            status["db"] = "ok"
        except Exception as exc:
            status["db"] = f"error: {exc}"

        try:
            self._minio.list_buckets()
            status["minio"] = "ok"
        except Exception as exc:
            status["minio"] = f"error: {exc}"

        return status


# ---------------------------------------------------------------------------
# CLI smoke-test  (python -m backend.data_lake RELIANCE.NS)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    sym = sys.argv[1] if len(sys.argv) > 1 else "RELIANCE.NS"

    lake = DataLakeEngine()
    print("Health:", lake.health_check())

    print(f"\nSyncing {sym} …")
    sync_result = lake.sync_external_data(sym)
    print("Sync result:", sync_result)

    print(f"\nQuerying cached data for {sym} …")
    payload = lake.query_cached_data(sym)
    print(f"Rows: {payload['rows']}  |  Docs: {payload['docs']}")
    if not payload["ohlcv"].empty:
        print(payload["ohlcv"].tail(3))


# ---------------------------------------------------------------------------
# Singleton engine (avoid creating a new DB pool per request)
# ---------------------------------------------------------------------------
_data_lake_engine: Optional[DataLakeEngine] = None


def _get_engine() -> DataLakeEngine:
    global _data_lake_engine
    if _data_lake_engine is None:
        _data_lake_engine = DataLakeEngine()
    return _data_lake_engine


# ---------------------------------------------------------------------------
# Async adapter for orchestrator
# ---------------------------------------------------------------------------
def _fetch_live_ohlcv(symbol: str) -> dict:
    """
    Fallback: fetch OHLCV directly from yfinance when the DB cache is empty.
    Returns the same dict shape as DataLakeEngine.query_cached_data().
    """
    try:
        ticker = yf.Ticker(symbol)
        raw_df = ticker.history(period="1y", interval="1d", auto_adjust=False)
        if raw_df is None or raw_df.empty:
            logger.warning("[%s] yfinance returned empty DataFrame in fallback.", symbol)
            return {
                "symbol": symbol,
                "ohlcv": pd.DataFrame(columns=["ts_utc", "ts_ist", "open", "high", "low", "close", "adj_close", "volume"]),
                "documents": [],
                "queried_at": datetime.now(tz=UTC),
                "rows": 0,
                "docs": 0,
            }

        # Normalise columns
        col_map = {"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume", "Adj Close": "adj_close"}
        df = raw_df.rename(columns=col_map)
        keep = [c for c in col_map.values() if c in df.columns]
        df = df[keep]

        # Normalise timestamps
        idx = df.index
        if idx.tz is None:
            idx = idx.tz_localize("UTC")
        else:
            idx = idx.tz_convert("UTC")
        df.index = idx
        df.index.name = "ts_utc"
        df["ts_utc"] = df.index
        df["ts_ist"] = df["ts_utc"].dt.tz_convert(IST)

        # Drop fully-null OHLCV rows
        ohlcv_cols = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
        df.dropna(subset=ohlcv_cols, how="all", inplace=True)
        df.reset_index(drop=True, inplace=True)

        # Set ts_utc as the index (same shape as query_cached_data output)
        df = df.set_index("ts_utc")

        logger.info("[%s] Fallback yfinance fetch: %d rows", symbol, len(df))
        return {
            "symbol": symbol,
            "ohlcv": df,
            "documents": [],
            "queried_at": datetime.now(tz=UTC),
            "rows": len(df),
            "docs": 0,
        }
    except Exception as exc:
        logger.error("[%s] yfinance fallback failed: %s", symbol, exc)
        return {
            "symbol": symbol,
            "ohlcv": pd.DataFrame(columns=["ts_utc", "ts_ist", "open", "high", "low", "close", "adj_close", "volume"]),
            "documents": [],
            "queried_at": datetime.now(tz=UTC),
            "rows": 0,
            "docs": 0,
        }


async def fetch_market_data(
    symbol: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> dict:
    """
    Async helper wrapper used by the orchestrator.
    Uses a singleton DataLakeEngine and calls the synchronous
    `query_cached_data` on a background thread, returning the
    same dict payload.  Falls back to live yfinance if the DB
    cache is empty.
    """
    try:
        engine = _get_engine()
        result = await asyncio.to_thread(engine.query_cached_data, symbol, start_date, end_date)
        # If the cache is empty, fall back to live data
        ohlcv = result.get("ohlcv")
        if ohlcv is None or (hasattr(ohlcv, "empty") and ohlcv.empty):
            logger.info("[%s] DB cache empty — falling back to live yfinance.", symbol)
            return await asyncio.to_thread(_fetch_live_ohlcv, symbol)
        return result
    except Exception as exc:
        logger.warning("[%s] DB query failed (%s) — falling back to live yfinance.", symbol, exc)
        return await asyncio.to_thread(_fetch_live_ohlcv, symbol)