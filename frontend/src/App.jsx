import { BrowserRouter, Routes, Route } from "react-router-dom"
import { ApiProvider } from "./context/ApiContext"

import LandingPage from "./pages/LandingPage"
import Dashboard from "./pages/Dashboard"
import Watchlist from "./pages/Watchlist"
import BounceAnalysis from "./pages/BounceAnalysis"

import Navbar from "./components/Navbar"

export default function App() {
  return (
    <ApiProvider>
      <BrowserRouter>
        <div className="min-h-screen bg-[#0a0a0f] text-white">
          <Navbar />

          <Routes>
            <Route path="/" element={<LandingPage />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/watchlist" element={<Watchlist />} />
            <Route path="/bounce" element={<BounceAnalysis />} />
          </Routes>
        </div>
      </BrowserRouter>
    </ApiProvider>
  )
}