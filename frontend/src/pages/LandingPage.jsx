import { useNavigate } from "react-router-dom"

export default function LandingPage() {
  const navigate = useNavigate()

  return (
    <div className="w-full min-h-screen bg-[#0a0a0f] flex items-center justify-center px-6">
      
      {/* Hero Container */}
      <div className="text-center max-w-3xl">
        
        {/* Title */}
        <h1 className="text-5xl md:text-6xl font-bold text-white mb-6">
          BounceRadar
        </h1>

        {/* Subtitle */}
        <p className="text-gray-400 text-lg md:text-xl mb-8">
          Institutional-grade bounce detection for retail traders
        </p>

        {/* CTA */}
        <button
          onClick={() => navigate("/dashboard")}
          className="px-6 py-3 bg-blue-500 hover:bg-blue-600 rounded-lg text-white font-medium transition"
        >
          Analyze a Stock →
        </button>

      </div>
    </div>
  )
}