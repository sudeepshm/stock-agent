import { useEffect, useState } from "react"
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts"
import { useApi } from "../context/ApiContext"

export default function CandlestickView() {
  const { currentTicker, fetchOHLCV } = useApi()

  const [data, setData] = useState([])
  const [range, setRange] = useState(90)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      const res = await fetchOHLCV(currentTicker, range)

      // add moving average
      const withMA = res.map((d, i, arr) => {
        const slice = arr.slice(Math.max(0, i - 20), i + 1)
        const avg =
          slice.reduce((sum, x) => sum + x.close, 0) /
          slice.length

        return { ...d, ma: avg }
      })

      setData(withMA)
      setLoading(false)
    }

    load()
  }, [currentTicker, range])

  const ranges = [30, 60, 90]

  return (
    <div className="bg-[#12121e] p-6 rounded-xl border border-[#1e1e3a] space-y-4">

      {/* Header */}
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-semibold">
          Price Chart
        </h3>

        {/* Range Toggle */}
        <div className="flex gap-2">
          {ranges.map((r) => (
            <button
              key={r}
              onClick={() => setRange(r)}
              className={`px-3 py-1 text-sm rounded ${
                range === r
                  ? "bg-blue-500"
                  : "bg-[#1e1e3a]"
              }`}
            >
              {r}D
            </button>
          ))}
        </div>
      </div>

      {/* Loading */}
      {loading && (
        <p className="text-gray-400 text-sm">
          Loading chart...
        </p>
      )}

      {/* Chart */}
      {!loading && data.length > 0 && (
        <div className="w-full h-[300px]">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data}>
              <XAxis dataKey="date" hide />
              <YAxis domain={["auto", "auto"]} />
              <Tooltip />

              {/* Price */}
              <Line
                type="monotone"
                dataKey="close"
                stroke="#3b82f6"
                dot={false}
              />

              {/* Moving Average */}
              <Line
                type="monotone"
                dataKey="ma"
                stroke="#22c55e"
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Stats */}
      {!loading && data.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">

          <Stat label="Latest Price" value={data.at(-1)?.close?.toFixed(2)} />
          <Stat label="High" value={Math.max(...data.map(d => d.high)).toFixed(2)} />
          <Stat label="Low" value={Math.min(...data.map(d => d.low)).toFixed(2)} />
          <Stat label="Points" value={data.length} />

        </div>
      )}

    </div>
  )
}

/* Stat Chip */
function Stat({ label, value }) {
  return (
    <div className="bg-[#1e1e3a] p-3 rounded">
      <p className="text-gray-400 text-xs">{label}</p>
      <p className="font-semibold">{value}</p>
    </div>
  )
}