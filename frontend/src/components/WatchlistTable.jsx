import { useEffect, useState } from "react"

const STORAGE_KEY = "bounceradar_watchlist"

export default function Watchlist() {
  const [input, setInput] = useState("")
  const [watchlist, setWatchlist] = useState([])

  // Load from localStorage
  useEffect(() => {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) {
      setWatchlist(JSON.parse(saved))
    }
  }, [])

  // Save to localStorage
  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(watchlist))
  }, [watchlist])

  // Validate ticker
  const isValidTicker = (ticker) => {
    return /^[A-Z0-9&\-\.]{1,20}$/.test(ticker)
  }

  // Add ticker
  const handleAdd = () => {
    const ticker = input.trim().toUpperCase()

    if (!isValidTicker(ticker)) {
      alert("Invalid ticker (1–5 uppercase letters)")
      return
    }

    if (watchlist.includes(ticker)) {
      alert("Already in watchlist")
      return
    }

    if (watchlist.length >= 20) {
      alert("Max 20 tickers allowed")
      return
    }

    setWatchlist([...watchlist, ticker])
    setInput("")
  }

  // Remove ticker
  const handleRemove = (ticker) => {
    setWatchlist(watchlist.filter((t) => t !== ticker))
  }

  return (
    <div className="p-6 space-y-6">

      {/* Add Bar */}
      <div className="flex gap-3">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Enter ticker (e.g., AAPL)"
          className="flex-1 px-4 py-2 bg-[#12121e] border border-[#1e1e3a] rounded-lg text-white outline-none"
        />
        <button
          onClick={handleAdd}
          className="px-4 py-2 bg-blue-500 hover:bg-blue-600 rounded-lg"
        >
          Add Ticker
        </button>
      </div>

      {/* Quick Add */}
      <div className="flex flex-wrap gap-2">
        {["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ITC.NS"].map((t) => (
          <button
            key={t}
            onClick={() => setInput(t)}
            className="px-3 py-1 bg-[#1e1e3a] rounded text-sm hover:bg-blue-500"
          >
            {t}
          </button>
        ))}
      </div>

      {/* Empty State */}
      {watchlist.length === 0 && (
        <div className="text-center text-gray-400 mt-10">
          Your watchlist is empty. Add a ticker above.
        </div>
      )}

      {/* Table */}
      {watchlist.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left border border-[#1e1e3a]">
            <thead className="bg-[#12121e] text-gray-400">
              <tr>
                <th className="p-3">#</th>
                <th className="p-3">Ticker</th>
                <th className="p-3">Actions</th>
              </tr>
            </thead>

            <tbody>
              {watchlist.map((ticker, index) => (
                <tr
                  key={ticker}
                  className="border-t border-[#1e1e3a] hover:bg-[#1e1e3a]"
                >
                  <td className="p-3">{index + 1}</td>
                  <td className="p-3 font-mono text-blue-400">
                    {ticker}
                  </td>
                  <td className="p-3">
                    <button
                      onClick={() => handleRemove(ticker)}
                      className="text-red-400 hover:text-red-500"
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>

          </table>
        </div>
      )}
    </div>
  )
}