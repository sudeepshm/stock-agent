export default function StatusBanner({
    type = "info",
    message = "",
  }) {
    if (!message) return null
  
    const styles = {
      info: "bg-blue-500/10 text-blue-400 border-blue-500/30",
      success: "bg-green-500/10 text-green-400 border-green-500/30",
      error: "bg-red-500/10 text-red-400 border-red-500/30",
      warning: "bg-amber-500/10 text-amber-400 border-amber-500/30",
    }
  
    return (
      <div
        className={`w-full p-3 rounded-lg border text-sm ${styles[type]}`}
      >
        {message}
      </div>
    )
  }