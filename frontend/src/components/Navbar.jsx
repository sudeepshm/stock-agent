import { useState } from "react"
import { useNavigate, NavLink } from "react-router-dom"
import { useApi } from "../context/ApiContext"

export default function Navbar() {
  const [ticker, setTicker] = useState("")
  const { analyze, jobStatus, loading } = useApi()
  const navigate = useNavigate()

  function handleSearch(e) {
    e.preventDefault()
    if (!ticker.trim()) return
    analyze(ticker.trim())
    navigate("/dashboard")
    setTicker("")
  }

  const linkClass = ({ isActive }) =>
    `text-xs font-mono px-3 py-1.5 rounded border transition-all ${
      isActive
        ? "text-saffron border-saffron bg-saffron/10"
        : "text-slate-400 border-transparent hover:text-saffron"
    }`

  return (
    <nav className="sticky top-0 z-50 bg-navy-800 border-b border-navy-600 px-6 py-3 flex items-center gap-4">
      <NavLink to="/" className="font-mono font-semibold text-lg tracking-widest shrink-0">
        <span className="text-saffron">MARKET</span>
        <span className="text-white">RADAR</span>
      </NavLink>

      <form onSubmit={handleSearch} className="flex gap-2 flex-1 max-w-sm">
        <input
          value={ticker}
          onChange={e => setTicker(e.target.value.toUpperCase())}
          placeholder="RELIANCE.NS, TCS.NS, HDFCBANK.BO"
          className="flex-1 bg-navy-700 border border-navy-600 focus:border-saffron rounded px-3 py-1.5 text-sm font-mono text-white placeholder-slate-500 focus:outline-none transition-colors"
        />
        <button
          type="submit"
          disabled={loading}
          className="bg-saffron disabled:opacity-50 text-navy-900 font-mono font-semibold text-sm px-4 py-1.5 rounded hover:bg-saffron-dark transition-colors"
        >
          {loading ? "..." : "GO"}
        </button>
      </form>

      {jobStatus === "PROCESSING" && (
        <span className="font-mono text-xs text-saffron animate-pulse">Analyzing...</span>
      )}

      <div className="flex gap-1 ml-auto">
        <NavLink to="/"          className={linkClass}>HOME</NavLink>
        <NavLink to="/dashboard" className={linkClass}>DASHBOARD</NavLink>
        <NavLink to="/watchlist" className={linkClass}>WATCHLIST</NavLink>
        <NavLink to="/bounce"    className={linkClass}>BOUNCE?</NavLink>
      </div>
    </nav>
  )
}