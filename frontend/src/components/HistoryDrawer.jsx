export default function HistoryDrawer({
    open,
    onClose,
    history = [],
    ticker,
  }) {
    if (!open) return null
  
    return (
      <div className="fixed inset-0 z-50 flex">
  
        {/* Overlay */}
        <div
          className="flex-1 bg-black/50"
          onClick={onClose}
        />
  
        {/* Drawer */}
        <div className="w-full max-w-md bg-[#12121e] border-l border-[#1e1e3a] p-6 overflow-y-auto">
  
          {/* Header */}
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold">
              {ticker} History
            </h2>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-white"
            >
              ✕
            </button>
          </div>
  
          {/* Empty */}
          {history.length === 0 && (
            <p className="text-gray-400 text-sm">
              No history available.
            </p>
          )}
  
          {/* List */}
          {history.length > 0 && (
            <div className="space-y-3">
              {history.map((item, i) => (
                <div
                  key={i}
                  className="p-3 bg-[#1e1e3a] rounded"
                >
                  <div className="flex justify-between text-sm">
                    <span>{item.date}</span>
                    <span
                      className={
                        item.signal === "BULLISH"
                          ? "text-green-400"
                          : item.signal === "BEARISH"
                          ? "text-red-400"
                          : "text-gray-400"
                      }
                    >
                      {item.signal}
                    </span>
                  </div>
  
                  <div className="text-xs text-gray-400 mt-1">
                    Confidence: {item.confidence ?? "—"}%
                  </div>
                </div>
              ))}
            </div>
          )}
  
        </div>
      </div>
    )
  }