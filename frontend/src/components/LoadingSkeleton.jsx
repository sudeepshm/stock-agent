export default function LoadingSkeleton({ lines = 3 }) {
    return (
      <div className="animate-pulse space-y-3">
        
        {Array.from({ length: lines }).map((_, i) => (
          <div
            key={i}
            className="h-4 w-full bg-[#1e1e3a] rounded"
          />
        ))}
  
      </div>
    )
  }