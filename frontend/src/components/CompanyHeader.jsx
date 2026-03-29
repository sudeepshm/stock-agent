import { useState } from "react"

export default function CompanyHeader({ company, ticker, onRefresh }) {
  const [refreshing, setRefreshing] = useState(false)

  const handleRefresh = async () => {
    if (!onRefresh) return

    setRefreshing(true)
    await onRefresh()
    setRefreshing(false)
  }

  const initials = ticker?.slice(0, 2).toUpperCase()

  return (
    <div className="bg-[#12121e] p-6 rounded-xl border border-[#1e1e3a] flex items-center justify-between">

      {/* Left */}
      <div className="flex items-center gap-4">

        {/* Logo / Fallback */}
        <div className="w-12 h-12 rounded-full bg-blue-500 flex items-center justify-center font-bold text-white">
          {initials}
        </div>

        {/* Info */}
        <div>
          <h2 className="text-xl font-semibold">
            {company?.name || ticker}
          </h2>

          <div className="flex gap-3 text-sm text-gray-400 mt-1">
            <span className="px-2 py-0.5 bg-[#1e1e3a] rounded">
              {ticker}
            </span>
            <span>{company?.sector || "—"}</span>
            <span>{company?.marketCap || "—"}</span>
          </div>
        </div>

      </div>

      {/* Right */}
      <button
        onClick={handleRefresh}
        className={`px-3 py-1 rounded bg-[#1e1e3a] text-sm ${
          refreshing ? "animate-spin" : ""
        }`}
      >
        ⟳
      </button>

    </div>
  )
}