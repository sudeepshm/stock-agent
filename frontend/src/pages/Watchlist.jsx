import WatchlistTable from "../components/WatchlistTable"

export default function Watchlist() {
  return (
    <main className="min-h-screen px-4 py-6 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-4xl">
        <h1 className="text-2xl font-bold text-white mb-6">Your Watchlist</h1>
        <WatchlistTable />
      </div>
    </main>
  )
}
