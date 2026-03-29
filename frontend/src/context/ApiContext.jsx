import { createContext, useContext, useState, useCallback } from "react"

const ApiContext = createContext()

const API_BASE = import.meta.env.VITE_API_BASE || ""

// ─── Low-level fetch helper ──────────────────────────────────────────────────
async function apiFetch(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, options)
  if (!res.ok) {
    const body = await res.text().catch(() => "")
    throw new Error(`API ${res.status}: ${body || res.statusText}`)
  }
  return res.json()
}

// ─── Polling helper for /report endpoint ────────────────────────────────────
async function pollReport(jobId, onStatus, maxAttempts = 30, intervalMs = 1500) {
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise(r => setTimeout(r, intervalMs))
    const data = await apiFetch(`/report/${jobId}`)
    if (onStatus) onStatus(data.status)
    if (data.status === "COMPLETED") return data
    if (data.status === "FAILED") {
      const errMsg = data.error_logs?.join("; ") || "Job failed"
      throw new Error(errMsg)
    }
  }
  throw new Error("Timed out waiting for analysis")
}

// ─── Provider ────────────────────────────────────────────────────────────────
export function ApiProvider({ children }) {
  const [report, setReport]             = useState(null)
  const [loading, setLoading]           = useState(false)
  const [error, setError]               = useState(null)
  const [jobStatus, setJobStatus]       = useState(null)
  const [currentTicker, setCurrentTicker] = useState("")
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [lastUpdated, setLastUpdated]   = useState(null)

  // ── Full analysis pipeline (POST /analyze → poll /report) ──────────────
  const analyze = useCallback(async (ticker) => {
    const t = ticker.trim().toUpperCase()
    setLoading(true)
    setError(null)
    setReport(null)
    setJobStatus("PENDING")
    setCurrentTicker(t)

    try {
      const postRes = await apiFetch(`/analyze/${t}`, { method: "POST" })
      const jobId = postRes.job_id

      setJobStatus("PROCESSING")
      const result = await pollReport(jobId, setJobStatus)
      setReport(result)
      setJobStatus("COMPLETED")
      setLastUpdated(new Date().toISOString())
    } catch (e) {
      setError(e.message)
      setJobStatus("FAILED")
    } finally {
      setLoading(false)
    }
  }, [])

  // ── Fetch OHLCV candle data ────────────────────────────────────────────
  const fetchOHLCV = useCallback(async (symbol, days = 90) => {
    const data = await apiFetch(`/api/ohlcv?symbol=${encodeURIComponent(symbol)}&days=${days}`)
    // Map backend response to chart-friendly format
    return data.map(d => ({
      date: d.time?.split("T")[0] || d.time,
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
      volume: d.volume,
      ma20: d.ma20,
    }))
  }, [])

  // ── Fetch company info ─────────────────────────────────────────────────
  const fetchCompanyInfo = useCallback(async (symbol) => {
    return await apiFetch(`/api/company?symbol=${encodeURIComponent(symbol)}`)
  }, [])

  // ── Fetch signals ──────────────────────────────────────────────────────
  const fetchSignals = useCallback(async (symbol) => {
    return await apiFetch(`/api/signals?symbol=${encodeURIComponent(symbol)}`)
  }, [])

  // ── Fetch bounce history ───────────────────────────────────────────────
  const fetchBounceHistory = useCallback(async (symbol, limit = 20) => {
    return await apiFetch(`/api/bounce_history?symbol=${encodeURIComponent(symbol)}&limit=${limit}`)
  }, [])

  // ── Refresh: re-fetch signals + company for current ticker ─────────────
  const refreshTicker = useCallback(async (symbol) => {
    setIsRefreshing(true)
    try {
      // re-fetch triggers the backend to pull fresh data
      await Promise.all([
        fetchSignals(symbol),
        fetchCompanyInfo(symbol),
      ])
      setLastUpdated(new Date().toISOString())
    } finally {
      setIsRefreshing(false)
    }
  }, [fetchSignals, fetchCompanyInfo])

  return (
    <ApiContext.Provider value={{
      // Data
      report,
      currentTicker,
      // Loading state
      loading,
      error,
      jobStatus,
      isRefreshing,
      lastUpdated,
      // Actions
      analyze,
      fetchOHLCV,
      fetchCompanyInfo,
      fetchSignals,
      fetchBounceHistory,
      refreshTicker,
    }}>
      {children}
    </ApiContext.Provider>
  )
}

export const useApi = () => useContext(ApiContext)
