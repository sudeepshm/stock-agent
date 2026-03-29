import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { useApi } from "../context/ApiContext";

// ─── Utility ──────────────────────────────────────────────────────────────────
const cn = (...classes) => classes.filter(Boolean).join(" ");

const fadeUp = (delay = 0) => ({
  initial: { opacity: 0, y: 24 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.5, delay, ease: [0.22, 1, 0.36, 1] },
});

// ─── Sub-components ───────────────────────────────────────────────────────────

/** CompanyHeader */
function CompanyHeader({ company, lastUpdated, onRefresh, isRefreshing }) {
  const initials = company?.ticker?.slice(0, 2) || "??";
  const colors = ["#6366f1", "#8b5cf6", "#ec4899", "#14b8a6", "#f59e0b"];
  const colorIdx = initials.charCodeAt(0) % colors.length;
  const accentColor = colors[colorIdx];

  return (
    <div
      className="relative overflow-hidden rounded-2xl border border-white/5 px-6 py-5"
      style={{ background: "linear-gradient(135deg,#12121e 60%,#1a1a2e)" }}
    >
      <div
        className="pointer-events-none absolute -top-10 -left-10 h-40 w-40 rounded-full blur-3xl opacity-20"
        style={{ background: accentColor }}
      />
      <div className="relative flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-4">
          {company?.logoUrl ? (
            <img src={company.logoUrl} alt={company.name} className="h-12 w-12 rounded-xl object-contain bg-white/10 p-1" />
          ) : (
            <div
              className="flex h-12 w-12 items-center justify-center rounded-xl text-sm font-black tracking-widest text-white shadow-lg"
              style={{ background: `linear-gradient(135deg,${accentColor}cc,${accentColor}44)`, border: `1px solid ${accentColor}55` }}
            >
              {initials}
            </div>
          )}
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-xl font-extrabold text-white tracking-tight leading-none">
                {company?.name || "Loading…"}
              </h1>
              <span className="rounded-md bg-white/10 px-2 py-0.5 text-xs font-mono font-bold text-slate-300 border border-white/10">
                {company?.ticker || "—"}
              </span>
            </div>
            <div className="mt-1.5 flex items-center gap-2 flex-wrap">
              {company?.sector && (
                <span
                  className="rounded-full px-2.5 py-0.5 text-[11px] font-semibold"
                  style={{ background: `${accentColor}22`, color: accentColor, border: `1px solid ${accentColor}44` }}
                >
                  {company.sector}
                </span>
              )}
              {company?.marketCap && company.marketCap !== "N/A" && (
                <span className="rounded-full bg-emerald-500/10 border border-emerald-500/20 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-400">
                  MCap {company.marketCap}
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3 ml-auto">
          <div className="text-right">
            <p className="text-[10px] uppercase tracking-widest text-slate-500 font-semibold">Last Updated</p>
            <p className="text-xs text-slate-300 font-mono">{lastUpdated || "—"}</p>
          </div>
          <button
            onClick={onRefresh}
            disabled={isRefreshing}
            className="flex h-9 w-9 items-center justify-center rounded-xl bg-white/5 border border-white/10 hover:bg-white/10 transition-all active:scale-95"
            title="Refresh data"
          >
            <svg
              className={cn("h-4 w-4 text-slate-300", isRefreshing && "animate-spin")}
              fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h5M20 20v-5h-5M4 9a8 8 0 0115.54-2.46M20 15a8 8 0 01-15.54 2.46" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}

/** SignalCard */
function SignalCard({ signalData }) {
  if (!signalData) return <div className="rounded-2xl border border-white/5 p-6 bg-[#12121e] text-slate-500">Loading signals…</div>;

  const { direction, confidence, signals } = signalData;
  const isBullish = direction === "BULLISH";
  const glowColor = isBullish ? "#22c55e" : direction === "BEARISH" ? "#ef4444" : "#6366f1";
  const confidenceColor = confidence >= 70 ? "#22c55e" : confidence >= 41 ? "#f59e0b" : "#ef4444";

  const signalRows = [
    { key: "rsiOversold", label: "RSI Oversold" },
    { key: "macdCross", label: "MACD Cross" },
    { key: "volumeSpike", label: "Volume Spike" },
    { key: "supportTest", label: "Support Test" },
    { key: "patternMatch", label: "Pattern Match" },
  ];

  return (
    <div className="relative overflow-hidden rounded-2xl border border-white/5 p-6 flex flex-col gap-5" style={{ background: "linear-gradient(160deg,#12121e,#0d1117)" }}>
      <div className="pointer-events-none absolute inset-0 rounded-2xl opacity-5" style={{ boxShadow: `inset 0 0 60px 10px ${glowColor}` }} />
      <div className="flex items-center gap-2">
        <svg className="h-4 w-4 text-amber-400" viewBox="0 0 24 24" fill="currentColor"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" /></svg>
        <span className="text-xs font-bold uppercase tracking-widest text-slate-400">Bounce Signal</span>
      </div>

      <div className="flex justify-center">
        <motion.div
          animate={{ boxShadow: [`0 0 20px 2px ${glowColor}55`, `0 0 40px 8px ${glowColor}22`, `0 0 20px 2px ${glowColor}55`] }}
          transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
          className="relative flex h-20 w-48 items-center justify-center rounded-2xl border font-black text-2xl tracking-[0.15em]"
          style={{
            background: isBullish ? "linear-gradient(135deg,#052e16,#14532d)" : "linear-gradient(135deg,#2c0808,#450a0a)",
            borderColor: `${glowColor}44`,
            color: glowColor,
          }}
        >
          {isBullish ? "▲ " : "▼ "}{direction}
        </motion.div>
      </div>

      <div>
        <div className="mb-1.5 flex justify-between text-xs">
          <span className="text-slate-400 font-semibold">Confidence</span>
          <span className="font-mono font-bold" style={{ color: confidenceColor }}>{confidence}%</span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-white/5">
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${confidence}%` }}
            transition={{ duration: 1, delay: 0.3, ease: "easeOut" }}
            className="h-full rounded-full"
            style={{ background: `linear-gradient(90deg, ${confidenceColor}88, ${confidenceColor})` }}
          />
        </div>
      </div>

      <div className="flex flex-col gap-2">
        {signalRows.map(({ key, label }) => {
          const active = signals?.[key];
          return (
            <div key={key} className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="h-1.5 w-1.5 rounded-full" style={{ background: active ? "#22c55e" : "#ef4444" }} />
                <span className="text-xs text-slate-400">{label}</span>
              </div>
              <span className="text-sm font-bold" style={{ color: active ? "#22c55e" : "#ef4444" }}>
                {active ? "✓" : "✗"}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** Circular Arc SVG for reliability */
function ArcProgress({ value, size = 80, strokeWidth = 8 }) {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (value / 100) * circumference;
  const color = value >= 75 ? "#f59e0b" : value >= 50 ? "#6366f1" : "#64748b";

  return (
    <svg width={size} height={size} className="-rotate-90">
      <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="#ffffff08" strokeWidth={strokeWidth} />
      <motion.circle
        cx={size / 2} cy={size / 2} r={radius}
        fill="none" stroke={color} strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeDasharray={circumference}
        initial={{ strokeDashoffset: circumference }}
        animate={{ strokeDashoffset: offset }}
        transition={{ duration: 1.2, delay: 0.5, ease: "easeOut" }}
      />
    </svg>
  );
}

/** ChartPatternCard */
function ChartPatternCard({ pattern }) {
  if (!pattern || !pattern.name) {
    return (
      <div className="rounded-2xl border border-white/5 p-6 bg-[#12121e] text-slate-500">
        No pattern detected
      </div>
    );
  }

  const { name, confidence, description } = pattern;
  const isVerified = confidence > 75;

  return (
    <div className="relative overflow-hidden rounded-2xl border border-white/5 p-6 flex flex-col gap-5" style={{ background: "linear-gradient(160deg,#12121e,#0d1117)" }}>
      <div className="flex items-center gap-2">
        <svg className="h-4 w-4 text-violet-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
        </svg>
        <span className="text-xs font-bold uppercase tracking-widest text-slate-400">Detected Pattern</span>
      </div>

      <div>
        <h2 className="text-2xl font-black text-white tracking-tight">{name}</h2>
        {isVerified && (
          <motion.div
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.4 }}
            className="mt-2 inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-bold border"
            style={{ background: "linear-gradient(90deg,#78350f22,#92400e44)", borderColor: "#f59e0b44", color: "#fbbf24" }}
          >
            <svg className="h-3 w-3" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12 1l2.9 6.26L22 8.27l-5 4.87 1.18 6.88L12 16.77l-6.18 3.25L7 13.14 2 8.27l7.1-1.01L12 1z" />
            </svg>
            Double-Lock ✓ Verified
          </motion.div>
        )}
      </div>

      <div className="flex items-center gap-4">
        <div className="relative flex-shrink-0">
          <ArcProgress value={confidence || 0} size={84} strokeWidth={7} />
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-base font-black" style={{ color: (confidence || 0) >= 75 ? "#f59e0b" : "#6366f1" }}>
              {confidence || 0}%
            </span>
            <span className="text-[9px] text-slate-500 font-semibold uppercase tracking-wide">reliability</span>
          </div>
        </div>
        <p className="text-sm text-slate-400 leading-relaxed">{description || "Pattern analysis pending."}</p>
      </div>
    </div>
  );
}

/** Custom Candlestick Tooltip */
function CandleTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload;
  if (!d) return null;
  const isBull = d.close >= d.open;
  return (
    <div className="rounded-xl border border-white/10 bg-[#1a1a2e]/95 backdrop-blur p-3 text-xs shadow-2xl">
      <p className="mb-2 font-bold text-slate-300">{label}</p>
      {[
        ["Open", d.open, isBull ? "#22c55e" : "#ef4444"],
        ["High", d.high, "#94a3b8"],
        ["Low", d.low, "#94a3b8"],
        ["Close", d.close, isBull ? "#22c55e" : "#ef4444"],
      ].map(([k, v, c]) => (
        <div key={k} className="flex justify-between gap-4">
          <span className="text-slate-500">{k}</span>
          <span className="font-mono font-bold" style={{ color: c }}>₹{v?.toFixed(2)}</span>
        </div>
      ))}
      {d.ma20 != null && (
        <div className="mt-1 flex justify-between gap-4 border-t border-white/5 pt-1">
          <span className="text-slate-500">MA20</span>
          <span className="font-mono font-bold text-violet-400">₹{d.ma20?.toFixed(2)}</span>
        </div>
      )}
    </div>
  );
}

/** CandlestickView — connected to backend API */
function CandlestickView({ fetchOHLCV, ticker }) {
  const [period, setPeriod] = useState(30);
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async (days) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchOHLCV(ticker, days);
      if (!res || res.length === 0) {
        setError("No OHLCV data available from backend.");
        setData([]);
      } else {
        setData(res);
      }
    } catch (e) {
      setError(e.message || "Failed to load chart data");
      setData([]);
    } finally {
      setLoading(false);
    }
  }, [fetchOHLCV, ticker]);

  useEffect(() => {
    if (ticker) load(period);
  }, [period, ticker, load]);

  const periods = [30, 60, 90];

  return (
    <div className="rounded-2xl border border-white/5 p-6" style={{ background: "linear-gradient(160deg,#12121e,#0d1117)" }}>
      <div className="mb-4 flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <svg className="h-4 w-4 text-sky-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
          </svg>
          <span className="text-xs font-bold uppercase tracking-widest text-slate-400">Price Action</span>
        </div>
        <div className="flex gap-1 rounded-xl bg-white/5 p-1 border border-white/5">
          {periods.map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={cn(
                "rounded-lg px-3 py-1 text-xs font-bold transition-all",
                period === p
                  ? "bg-violet-500/30 text-violet-300 border border-violet-500/30"
                  : "text-slate-400 hover:text-slate-200"
              )}
            >
              {p}D
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="h-64 w-full animate-pulse rounded-xl bg-white/5" />
      ) : error ? (
        <div className="h-64 flex items-center justify-center text-red-400 text-sm">{error}</div>
      ) : (
        <ResponsiveContainer width="100%" height={280}>
          <ComposedChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#ffffff08" />
            <XAxis
              dataKey="date"
              tick={{ fill: "#475569", fontSize: 10, fontFamily: "monospace" }}
              axisLine={false} tickLine={false}
              interval={Math.floor(data.length / 6)}
            />
            <YAxis
              tick={{ fill: "#475569", fontSize: 10, fontFamily: "monospace" }}
              axisLine={false} tickLine={false}
              tickFormatter={(v) => `₹${v}`}
              width={52}
            />
            <Tooltip content={<CandleTooltip />} />
            <Bar dataKey="close" maxBarSize={8} radius={[2, 2, 0, 0]}>
              {data.map((d, i) => (
                <Cell key={i} fill={d.close >= d.open ? "#22c55e" : "#ef4444"} />
              ))}
            </Bar>
            <Line type="monotone" dataKey="ma20" stroke="#818cf8" strokeWidth={1.5} dot={false} strokeDasharray="4 2" />
          </ComposedChart>
        </ResponsiveContainer>
      )}

      <div className="mt-3 flex items-center gap-4 text-[11px] text-slate-500">
        <div className="flex items-center gap-1.5"><div className="h-2 w-2 rounded-sm bg-emerald-500" />Bullish candle</div>
        <div className="flex items-center gap-1.5"><div className="h-2 w-2 rounded-sm bg-red-500" />Bearish candle</div>
        <div className="flex items-center gap-1.5"><div className="h-px w-5 bg-violet-400" style={{ borderTop: "2px dashed #818cf8" }} />MA 20</div>
      </div>
    </div>
  );
}

/** StatChips row */
function StatChips({ stats }) {
  if (!stats) return null;

  const chips = [
    {
      label: "Avg Volume", value: stats.avgVolume || "—",
      icon: <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6m6 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0h6" /></svg>,
      color: "#6366f1",
    },
    {
      label: "52W High", value: stats.week52High != null ? `₹${Number(stats.week52High).toFixed(2)}` : "—",
      icon: <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M5 10l7-7m0 0l7 7m-7-7v18" /></svg>,
      color: "#22c55e",
    },
    {
      label: "52W Low", value: stats.week52Low != null ? `₹${Number(stats.week52Low).toFixed(2)}` : "—",
      icon: <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M19 14l-7 7m0 0l-7-7m7 7V3" /></svg>,
      color: "#ef4444",
    },
    {
      label: "Volatility", value: stats.volatility != null ? `${stats.volatility}%` : "—",
      icon: <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>,
      color: "#f59e0b",
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {chips.map(({ label, value, icon, color }, i) => (
        <motion.div
          key={label}
          {...fadeUp(0.5 + i * 0.08)}
          className="flex items-center gap-3 rounded-xl border border-white/5 p-3"
          style={{ background: "#12121e" }}
        >
          <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg" style={{ background: `${color}18`, color }}>
            {icon}
          </div>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">{label}</p>
            <p className="text-sm font-black text-white font-mono">{value}</p>
          </div>
        </motion.div>
      ))}
    </div>
  );
}

/** Error banner */
function ErrorBanner({ message, onRetry }) {
  return (
    <div className="rounded-2xl border border-red-500/20 bg-red-500/5 p-8 text-center">
      <svg className="mx-auto h-10 w-10 text-red-400 mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
      </svg>
      <p className="text-red-400 font-semibold mb-1">Failed to Load Data</p>
      <p className="text-sm text-slate-500 mb-4">{message}</p>
      {onRetry && (
        <button onClick={onRetry} className="px-4 py-2 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm font-semibold hover:bg-red-500/20 transition">
          Retry
        </button>
      )}
    </div>
  );
}

/** Loading Skeleton */
function DashboardSkeleton() {
  const pulse = "animate-pulse rounded-xl bg-white/5";
  return (
    <div className="flex flex-col gap-5">
      <div className={`h-24 w-full ${pulse}`} />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className={`h-72 ${pulse}`} />
        <div className={`h-72 ${pulse}`} />
      </div>
      <div className={`h-72 w-full ${pulse}`} />
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[...Array(4)].map((_, i) => <div key={i} className={`h-16 ${pulse}`} />)}
      </div>
    </div>
  );
}

// ─── Main Dashboard Export ────────────────────────────────────────────────────
export default function Dashboard() {
  const {
    currentTicker,
    fetchOHLCV,
    fetchCompanyInfo,
    fetchSignals,
    isRefreshing: ctxIsRefreshing,
    lastUpdated: ctxLastUpdated,
    refreshTicker,
  } = useApi();

  const ticker = currentTicker || "RELIANCE.NS";

  const [signals, setSignals] = useState(null);
  const [company, setCompany] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState("");

  const loadData = useCallback(async () => {
    setError(null);
    try {
      const [sig, comp] = await Promise.all([
        fetchSignals(ticker),
        fetchCompanyInfo(ticker),
      ]);
      setSignals(sig);
      setCompany(comp);
      // Prefer server timestamp when available
      if (sig?.generatedAt) {
        setLastUpdated(new Date(sig.generatedAt).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }));
      }
    } catch (e) {
      setError(e.message || "Failed to connect to backend. Make sure the server is running.");
      setSignals(null);
      setCompany(null);
    }
    if (!signals?.generatedAt) {
      setLastUpdated(new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }));
    }
  }, [ticker, fetchSignals, fetchCompanyInfo]);

  useEffect(() => {
    setLoading(true);
    loadData().finally(() => setLoading(false));
  }, [loadData]);

  const handleRefresh = async () => {
    if (refreshTicker) {
      setIsRefreshing(true);
      await refreshTicker(ticker);
      setIsRefreshing(false);
      setLastUpdated(new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }));
      await loadData();
      return;
    }
    setIsRefreshing(true);
    await loadData();
    setIsRefreshing(false);
  };

  useEffect(() => {
    if (ctxIsRefreshing !== undefined) setIsRefreshing(ctxIsRefreshing);
    if (ctxLastUpdated) setLastUpdated(new Date(ctxLastUpdated).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }));
  }, [ctxIsRefreshing, ctxLastUpdated]);

  return (
    <main
      className="min-h-screen px-4 py-6 sm:px-6 lg:px-8"
      style={{
        background: "radial-gradient(ellipse at 20% 0%,#1e1b4b22 0%,transparent 60%), radial-gradient(ellipse at 80% 100%,#0f172a 0%,#080c14 100%)",
        fontFamily: "'DM Sans', 'Syne', sans-serif",
      }}
    >
      <div className="mx-auto max-w-6xl space-y-5">
        <AnimatePresence mode="wait">
          {loading ? (
            <motion.div key="skeleton" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
              <DashboardSkeleton />
            </motion.div>
          ) : error ? (
            <motion.div key="error" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
              <ErrorBanner message={error} onRetry={loadData} />
            </motion.div>
          ) : (
            <motion.div key="content" className="space-y-5">
              {/* Company Header */}
              <motion.div {...fadeUp(0)}>
                <CompanyHeader
                  company={company}
                  lastUpdated={lastUpdated}
                  onRefresh={handleRefresh}
                  isRefreshing={isRefreshing}
                />
              </motion.div>

              {/* Signal + Pattern cards grid */}
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                <motion.div {...fadeUp(0.1)}>
                  <SignalCard signalData={signals} />
                </motion.div>
                <motion.div {...fadeUp(0.2)}>
                  <ChartPatternCard pattern={signals?.pattern} />
                </motion.div>
              </div>

              {/* Candlestick Chart */}
              <motion.div {...fadeUp(0.3)}>
                <CandlestickView fetchOHLCV={fetchOHLCV} ticker={ticker} />
              </motion.div>

              {/* Stat Chips */}
              <StatChips stats={signals?.stats} />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </main>
  );
}
