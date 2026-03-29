import { useState } from "react"
import { useApi } from "../context/ApiContext"

/* =========================
   RSI (14-period)
========================= */
function calculateRSI(data, period = 14) {
  if (!data || data.length < period + 1) return null

  let gains = 0
  let losses = 0

  for (let i = 1; i <= period; i++) {
    const diff = data[i].close - data[i - 1].close
    if (diff >= 0) gains += diff
    else losses += Math.abs(diff)
  }

  const avgGain = gains / period
  const avgLoss = losses / period || 1

  const rs = avgGain / avgLoss
  return 100 - 100 / (1 + rs)
}

/* =========================
   EMA helper
========================= */
function calculateEMA(values, period) {
  if (!values || values.length === 0) return 0
  const k = 2 / (period + 1)
  let ema = values[0]

  for (let i = 1; i < values.length; i++) {
    ema = values[i] * k + ema * (1 - k)
  }

  return ema
}

/* =========================
   MACD
========================= */
function calculateMACD(data) {
  if (!data || data.length < 30) return null

  const closes = data.map((d) => d.close)

  const ema12 = calculateEMA(closes, 12)
  const ema26 = calculateEMA(closes, 26)
  const macd = ema12 - ema26

  return macd
}

/* =========================
   Volume Spike
========================= */
function volumeSpike(data) {
  if (!data || data.length < 20) return null

  const last = data[data.length - 1].volume
  const avg =
    data.slice(-20).reduce((sum, d) => sum + d.volume, 0) / 20

  return avg > 0 ? last / avg : null
}

/* =========================
   Support Level
========================= */
function supportLevel(data) {
  if (!data || data.length < 30) return null

  const closes = data.slice(-30).map((d) => d.close)
  const support = Math.min(...closes)
  const current = data[data.length - 1].close

  if (support === 0) return null
  const distance = ((current - support) / support) * 100

  return { support, distance }
}

/* =========================
   Main Component
========================= */
export default function BounceAnalysis() {
  const { fetchOHLCV } = useApi()

  const [ticker, setTicker] = useState("")
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const handleAnalyze = async () => {
    if (!ticker.trim()) return

    setLoading(true)
    setError(null)
    setData([])

    try {
      const ohlcv = await fetchOHLCV(ticker.trim().toUpperCase(), 90)
      if (!ohlcv || ohlcv.length === 0) {
        setError("No OHLCV data returned from backend. Check if the symbol is valid (e.g., RELIANCE.NS).")
      } else {
        setData(ohlcv)
      }
    } catch (e) {
      setError(e.message || "Failed to connect to backend. Make sure the server is running.")
    } finally {
      setLoading(false)
    }
  }

  // Calculations
  const rsi = calculateRSI(data)
  const macd = calculateMACD(data)
  const vol = volumeSpike(data)
  const support = supportLevel(data)

  const signals = [
    rsi !== null && rsi < 35,
    macd !== null && macd > 0,
    vol !== null && vol > 1.8,
    support && Math.abs(support.distance) < 3,
  ]

  const score =
    (signals.filter(Boolean).length / signals.length) * 100

  return (
    <main className="min-h-screen px-4 py-6 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-3xl space-y-6">
        <h1 className="text-2xl font-bold text-white">Bounce Analysis</h1>

        {/* Input */}
        <div className="flex gap-3">
          <input
            value={ticker}
            onChange={(e) => setTicker(e.target.value.toUpperCase())}
            onKeyDown={(e) => e.key === "Enter" && handleAnalyze()}
            placeholder="Enter ticker (e.g., RELIANCE.NS)"
            className="flex-1 px-4 py-2 bg-[#12121e] border border-[#1e1e3a] rounded-lg text-white font-mono focus:border-amber-500 focus:outline-none transition"
          />
          <button
            onClick={handleAnalyze}
            disabled={loading}
            className="px-5 py-2 bg-amber-500 hover:bg-amber-600 disabled:opacity-50 rounded-lg font-semibold text-navy-900 transition"
          >
            {loading ? "Analyzing…" : "Analyze"}
          </button>
        </div>

        {/* Error */}
        {error && (
          <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-4 text-sm text-red-400">
            {error}
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="space-y-3">
            <div className="h-24 w-full animate-pulse rounded-xl bg-white/5" />
            <div className="h-40 w-full animate-pulse rounded-xl bg-white/5" />
          </div>
        )}

        {/* Results */}
        {!loading && !error && data.length > 0 && (
          <div className="space-y-6">

            {/* Score */}
            <div className="bg-[#12121e] p-6 rounded-xl border border-[#1e1e3a]">
              <h2 className="text-lg font-semibold mb-2 text-slate-300">
                Bounce Score
              </h2>
              <p className="text-4xl font-black" style={{ color: score >= 75 ? "#22c55e" : score >= 50 ? "#f59e0b" : "#ef4444" }}>
                {score.toFixed(0)} / 100
              </p>
              <p className="text-xs text-slate-500 mt-1">
                Based on RSI, MACD, volume, and support proximity signals
              </p>
            </div>

            {/* Signals */}
            <div className="bg-[#12121e] p-6 rounded-xl border border-[#1e1e3a] space-y-3">
              <h3 className="text-sm font-bold uppercase tracking-widest text-slate-400 mb-2">Signal Breakdown</h3>

              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-300">RSI (14)</span>
                <span className={`font-mono font-bold text-sm ${rsi !== null && rsi < 35 ? "text-green-400" : "text-red-400"}`}>
                  {rsi != null ? `${rsi.toFixed(2)} → ${rsi < 35 ? "✓ Oversold" : "✗ Not oversold"}` : "N/A"}
                </span>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-300">MACD</span>
                <span className={`font-mono font-bold text-sm ${macd !== null && macd > 0 ? "text-green-400" : "text-red-400"}`}>
                  {macd != null ? `${macd.toFixed(2)} → ${macd > 0 ? "✓ Bullish" : "✗ Bearish"}` : "N/A"}
                </span>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-300">Volume Spike</span>
                <span className={`font-mono font-bold text-sm ${vol !== null && vol > 1.8 ? "text-green-400" : "text-red-400"}`}>
                  {vol != null ? `${vol.toFixed(2)}× → ${vol > 1.8 ? "✓ Spike" : "✗ Normal"}` : "N/A"}
                </span>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-300">Support Distance</span>
                <span className={`font-mono font-bold text-sm ${support && Math.abs(support.distance) < 3 ? "text-green-400" : "text-red-400"}`}>
                  {support ? `${support.distance.toFixed(2)}% → ${Math.abs(support.distance) < 3 ? "✓ Near support" : "✗ Far from support"}` : "N/A"}
                </span>
              </div>
            </div>
          </div>
        )}
      </div>
    </main>
  )
}