export default function BounceHistoryTable({ data = [] }) {
    if (!data.length) {
      return (
        <div className="bg-[#12121e] p-6 rounded-xl border border-[#1e1e3a] text-gray-400 text-sm">
          Insufficient historical signals in this window
        </div>
      )
    }
  
    const getColor = (value) => {
      if (value > 0) return "text-green-400"
      if (value < 0) return "text-red-400"
      return "text-gray-400"
    }
  
    return (
      <div className="bg-[#12121e] p-6 rounded-xl border border-[#1e1e3a]">
  
        {/* Title */}
        <h3 className="text-lg font-semibold mb-4">
          Past Signals & Outcomes
        </h3>
  
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
  
            {/* Header */}
            <thead className="text-gray-400">
              <tr>
                <th className="p-3 text-left">Date</th>
                <th className="p-3 text-left">Score</th>
                <th className="p-3 text-left">+5D</th>
                <th className="p-3 text-left">+10D</th>
                <th className="p-3 text-left">+15D</th>
              </tr>
            </thead>
  
            {/* Body */}
            <tbody>
              {data.map((row, i) => (
                <tr
                  key={i}
                  className="border-t border-[#1e1e3a] hover:bg-[#1e1e3a]"
                >
                  <td className="p-3">{row.date}</td>
  
                  <td className="p-3 font-semibold">
                    {row.score}
                  </td>
  
                  <td className={`p-3 ${getColor(row.d5)}`}>
                    {row.d5?.toFixed(2)}%
                  </td>
  
                  <td className={`p-3 ${getColor(row.d10)}`}>
                    {row.d10?.toFixed(2)}%
                  </td>
  
                  <td className={`p-3 ${getColor(row.d15)}`}>
                    {row.d15?.toFixed(2)}%
                  </td>
                </tr>
              ))}
            </tbody>
  
          </table>
        </div>
      </div>
    )
  }