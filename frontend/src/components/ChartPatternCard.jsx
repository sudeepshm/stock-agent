export default function ChartPatternCard({ pattern }) {
    if (!pattern) {
      return (
        <div className="bg-[#12121e] p-6 rounded-xl border border-[#1e1e3a]">
          <p className="text-gray-400">No pattern detected</p>
        </div>
      )
    }
  
    const { name, confidence, description } = pattern
  
    const isVerified = confidence > 75
  
    // Color based on confidence
    const getColor = () => {
      if (confidence <= 40) return "text-red-400"
      if (confidence <= 69) return "text-amber-400"
      return "text-green-400"
    }
  
    return (
      <div className="bg-[#12121e] p-6 rounded-xl border border-[#1e1e3a] space-y-4">
  
        {/* Title */}
        <h3 className="text-lg font-semibold">
          Detected Pattern
        </h3>
  
        {/* Pattern Name */}
        <div className={`text-2xl font-bold ${getColor()}`}>
          {name}
        </div>
  
        {/* Verified Badge */}
        {isVerified && (
          <div className="inline-block px-3 py-1 text-sm bg-amber-500/20 text-amber-400 border border-amber-500/30 rounded">
            ✓ Verified
          </div>
        )}
  
        {/* Confidence */}
        <div className="text-sm text-gray-400">
          Confidence: {confidence}%
        </div>
  
        {/* Description */}
        <p className="text-sm text-gray-300 leading-relaxed">
          {description}
        </p>
  
        {/* Circular Progress (simple SVG) */}
        <div className="flex items-center gap-4 mt-4">
  
          <svg width="60" height="60">
            <circle
              cx="30"
              cy="30"
              r="25"
              stroke="#1e1e3a"
              strokeWidth="5"
              fill="none"
            />
            <circle
              cx="30"
              cy="30"
              r="25"
              stroke="#3b82f6"
              strokeWidth="5"
              fill="none"
              strokeDasharray={157}
              strokeDashoffset={
                157 - (157 * confidence) / 100
              }
              strokeLinecap="round"
            />
          </svg>
  
          <div className="text-lg font-semibold">
            {confidence}%
          </div>
  
        </div>
  
      </div>
    )
  }