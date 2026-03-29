export default function BounceMeter({ score = 0 }) {
    const radius = 60
    const stroke = 10
    const normalizedRadius = radius - stroke * 0.5
    const circumference = normalizedRadius * 2 * Math.PI
  
    const offset =
      circumference - (score / 100) * circumference
  
    // Color logic
    const getColor = () => {
      if (score <= 39) return "#ef4444"   // red
      if (score <= 69) return "#f59e0b"   // amber
      return "#22c55e"                    // green
    }
  
    const label =
      score <= 39
        ? "NO SIGNAL"
        : score <= 69
        ? "WATCH"
        : "STRONG BUY"
  
    return (
      <div className="flex flex-col items-center justify-center">
  
        <svg height={radius * 2} width={radius * 2}>
  
          {/* Background */}
          <circle
            stroke="#1e1e3a"
            fill="transparent"
            strokeWidth={stroke}
            r={normalizedRadius}
            cx={radius}
            cy={radius}
          />
  
          {/* Progress */}
          <circle
            stroke={getColor()}
            fill="transparent"
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={`${circumference} ${circumference}`}
            strokeDashoffset={offset}
            r={normalizedRadius}
            cx={radius}
            cy={radius}
            style={{
              transition: "stroke-dashoffset 0.6s ease",
              transform: "rotate(-90deg)",
              transformOrigin: "50% 50%",
            }}
          />
  
        </svg>
  
        {/* Score */}
        <div className="mt-4 text-center">
          <div className="text-3xl font-bold">
            {score}
          </div>
          <div className="text-sm text-gray-400">
            / 100
          </div>
        </div>
  
        {/* Label */}
        <div
          className="mt-2 text-sm font-medium"
          style={{ color: getColor() }}
        >
          {label}
        </div>
  
      </div>
    )
  }