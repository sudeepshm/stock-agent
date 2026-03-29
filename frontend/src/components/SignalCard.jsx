export default function SignalCard({ signal }) {
    if (!signal) {
      return (
        <div className="bg-[#12121e] p-6 rounded-xl border border-[#1e1e3a]">
          <p className="text-gray-400">No signal data</p>
        </div>
      )
    }
  
    const { direction, confidence, signals } = signal
  
    // Confidence color
    const getColor = () => {
      if (confidence <= 40) return "bg-red-500"
      if (confidence <= 69) return "bg-amber-500"
      return "bg-green-500"
    }
  
    const badgeColor =
      direction === "BULLISH"
        ? "text-green-400"
        : direction === "BEARISH"
        ? "text-red-400"
        : "text-gray-400"
  
    const items = [
      { label: "RSI Oversold", value: signals?.rsiOversold },
      { label: "MACD Cross", value: signals?.macdCross },
      { label: "Volume Spike", value: signals?.volumeSpike },
      { label: "Support Test", value: signals?.supportTest },
      { label: "Pattern Match", value: signals?.patternMatch },
    ]
  
    return (
      <div className="bg-[#12121e] p-6 rounded-xl border border-[#1e1e3a] space-y-4">
  
        {/* Title */}
        <h3 className="text-lg font-semibold">
          ⚡ Bounce Signal
        </h3>
  
        {/* Direction */}
        <div className={`text-3xl font-bold ${badgeColor}`}>
          {direction}
        </div>
  
        {/* Confidence Bar */}
        <div>
          <div className="w-full h-2 bg-[#1e1e3a] rounded">
            <div
              className={`h-2 rounded ${getColor()}`}
              style={{ width: `${confidence}%` }}
            />
          </div>
          <p className="text-sm text-gray-400 mt-1">
            Confidence: {confidence}%
          </p>
        </div>
  
        {/* Signal Rows */}
        <div className="space-y-2 text-sm">
          {items.map((item) => (
            <div
              key={item.label}
              className="flex justify-between"
            >
              <span className="text-gray-300">
                {item.label}
              </span>
              <span
                className={
                  item.value ? "text-green-400" : "text-red-400"
                }
              >
                {item.value ? "✓" : "✗"}
              </span>
            </div>
          ))}
        </div>
  
      </div>
    )
  }