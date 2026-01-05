import React, { useMemo } from 'react'
import { AlertTriangle, TrendingUp, Target, List, Image as ImageIcon } from 'lucide-react'

// Reuse type from TrainingList to avoid circular dependency heaven if possible,
// or preferably import from a shared types file if refactored.
// For now, I'll assume the shape matches what we saw in TrainingList.
interface TrainingPoint {
  id: number
  imageUrl?: string
  rqiScore?: number // Model Score
  manualRqi?: number // Ground Truth
}

interface EvaluationDashboardProps {
  points: TrainingPoint[]
  onNavigate: (id: number) => void
}

const EvaluationDashboard: React.FC<EvaluationDashboardProps> = ({ points, onNavigate }) => {
  // Filter only points that have BOTH model score and manual score
  const validPoints = useMemo(() => {
    return points.filter(
      p => p.rqiScore !== undefined && p.manualRqi !== undefined && p.manualRqi !== null,
    )
  }, [points])

  // Calculate Metrics
  const metrics = useMemo(() => {
    if (validPoints.length === 0) return null

    let sumAbsError = 0
    let sumSqError = 0

    validPoints.forEach(p => {
      const diff = (p.rqiScore || 0) - (p.manualRqi || 0)
      sumAbsError += Math.abs(diff)
      sumSqError += diff * diff
    })

    const mae = sumAbsError / validPoints.length
    const rmse = Math.sqrt(sumSqError / validPoints.length)

    return { mae, rmse, count: validPoints.length }
  }, [validPoints])

  // Worst Offenders (Largest absolute error)
  const worstOffenders = useMemo(() => {
    return [...validPoints]
      .sort((a, b) => {
        const diffA = Math.abs((a.rqiScore || 0) - (a.manualRqi || 0))
        const diffB = Math.abs((b.rqiScore || 0) - (b.manualRqi || 0))
        return diffB - diffA
      })
      .slice(0, 10)
  }, [validPoints])

  // Scatter Plot Data Generation
  // Scale: 1-5 for both axes.
  // SVG Size: 300x300
  const CHART_SIZE = 300
  const PADDING = 40

  const getCoord = (value: number, id?: number) => {
    // Map 1..5 to PADDING..(SIZE-PADDING)
    const usefulWidth = CHART_SIZE - 2 * PADDING
    const normalized = (value - 1) / 4 // 0..1

    let offset = 0
    if (id !== undefined) {
      // Deterministic 'jitter' based on ID to avoid React purity issues and jumping dots on re-render
      // Math.sin(id) gives a deterministic value between -1 and 1
      offset = Math.sin(id * 12.9898) * 5
    }

    return PADDING + normalized * usefulWidth + offset
  }

  const getYCoord = (value: number, id?: number) => {
    const usefulWidth = CHART_SIZE - 2 * PADDING
    const normalized = (value - 1) / 4

    let offset = 0
    if (id !== undefined) {
      // Different seed/multiplier for Y to avoid diagonal lining
      offset = Math.cos(id * 78.233) * 5
    }

    // Y axis needs to be flipped (SVG 0 is top)
    return CHART_SIZE - PADDING - normalized * usefulWidth + offset
  }

  const getImageUrl = (url?: string) => {
    if (!url) return ''
    const filename = url.split('/').pop()
    return `http://localhost:8000/api/v1/images/${filename}`
  }

  if (!metrics) {
    return (
      <div className="flex flex-col items-center justify-center p-12 text-gray-500">
        <AlertTriangle size={48} className="mb-4 text-yellow-500" />
        <p>Not enough rated data to evaluate.</p>
        <p className="text-sm">
          Please manually rate some points that also have model predictions.
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full bg-[#111] text-white p-6 overflow-y-auto">
      <div className="flex items-center gap-3 mb-6">
        <TrendingUp className="text-blue-500" />
        <h2 className="text-xl font-bold">Model Evaluation Dashboard</h2>
      </div>

      {/* Metrics Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
        <div className="bg-[#222] p-4 rounded-lg border border-[#333]">
          <div className="text-gray-400 text-sm mb-1">Items Evaluated</div>
          <div className="text-2xl font-bold">
            {metrics.count}{' '}
            <span className="text-sm font-normal text-gray-500">of {points.length}</span>
          </div>
        </div>
        <div className="bg-[#222] p-4 rounded-lg border border-[#333]">
          <div className="text-gray-400 text-sm mb-1">MAE (Mean Absolute Error)</div>
          {/* Lower is better */}
          <div
            className={`text-2xl font-bold ${metrics.mae < 0.5 ? 'text-green-500' : metrics.mae < 1.0 ? 'text-yellow-500' : 'text-red-500'}`}>
            {metrics.mae.toFixed(3)}
          </div>
          <div className="text-xs text-gray-500 mt-1">Target: &lt; 0.5</div>
        </div>
        <div className="bg-[#222] p-4 rounded-lg border border-[#333]">
          <div className="text-gray-400 text-sm mb-1">RMSE (Root Mean Sq Error)</div>
          <div className="text-2xl font-bold text-blue-400">{metrics.rmse.toFixed(3)}</div>
          <div className="text-xs text-gray-500 mt-1">Penalizes large outlier errors</div>
        </div>
      </div>

      <div className="flex flex-col md:flex-row gap-8">
        {/* Chart Section */}
        <div className="flex-1 bg-[#222] p-4 rounded-lg border border-[#333] flex flex-col items-center">
          <h3 className="text-lg font-semibold mb-4 w-full text-left flex items-center gap-2">
            <Target size={16} />
            Prediction vs Truth
          </h3>

          <div className="relative">
            <svg width={CHART_SIZE} height={CHART_SIZE} className="overflow-visible">
              {/* Axes */}
              <line
                x1={PADDING}
                y1={CHART_SIZE - PADDING}
                x2={CHART_SIZE - PADDING}
                y2={CHART_SIZE - PADDING}
                stroke="#444"
                strokeWidth="2"
              />
              <line
                x1={PADDING}
                y1={CHART_SIZE - PADDING}
                x2={PADDING}
                y2={PADDING}
                stroke="#444"
                strokeWidth="2"
              />

              {/* Grid Lines & Labels */}
              {[1, 2, 3, 4, 5].map(tick => {
                const pos = getCoord(tick)
                const yPos = getYCoord(tick)
                return (
                  <React.Fragment key={tick}>
                    {/* X Axis Ticks */}
                    <line
                      x1={pos}
                      y1={CHART_SIZE - PADDING}
                      x2={pos}
                      y2={CHART_SIZE - PADDING + 5}
                      stroke="#666"
                    />
                    <text
                      x={pos}
                      y={CHART_SIZE - PADDING + 20}
                      textAnchor="middle"
                      fontSize="10"
                      fill="#888">
                      {tick}
                    </text>

                    {/* Y Axis Ticks */}
                    <line x1={PADDING - 5} y1={yPos} x2={PADDING} y2={yPos} stroke="#666" />
                    <text x={PADDING - 10} y={yPos + 3} textAnchor="end" fontSize="10" fill="#888">
                      {tick}
                    </text>

                    {/* Ideal Line (y=x) guide points */}
                    <circle cx={getCoord(tick)} cy={getYCoord(tick)} r="1" fill="#333" />
                  </React.Fragment>
                )
              })}

              {/* Ideal Line (Diagonal) */}
              <line
                x1={getCoord(1)}
                y1={getYCoord(1)}
                x2={getCoord(5)}
                y2={getYCoord(5)}
                stroke="#333"
                strokeWidth="1"
                strokeDasharray="4"
              />

              {/* Data Points */}
              {validPoints.map(p => (
                <circle
                  key={p.id}
                  cx={getCoord(p.manualRqi!, p.id)} // Add Jitter
                  cy={getYCoord(p.rqiScore!, p.id)} // Add Jitter
                  r="4"
                  fill="rgba(59, 130, 246, 0.4)" // More transparent for density
                  className="hover:r-6 hover:fill-blue-400 transition-all cursor-pointer"
                  onClick={() => onNavigate(p.id)}>
                  <title>
                    ID: {p.id} | Manual: {p.manualRqi} | Model: {p.rqiScore?.toFixed(2)}
                  </title>
                </circle>
              ))}

              {/* Labels */}
              <text
                x={CHART_SIZE / 2}
                y={CHART_SIZE - 5}
                textAnchor="middle"
                fontSize="12"
                fill="#888">
                Manual RQI (Truth)
              </text>
              <text
                x={10}
                y={CHART_SIZE / 2}
                textAnchor="middle"
                fontSize="12"
                fill="#888"
                transform={`rotate(-90, 10, ${CHART_SIZE / 2})`}>
                Model RQI (Predicted)
              </text>
            </svg>
          </div>
          <div className="mt-4 text-xs text-gray-500 text-center">
            Points on the diagonal line are perfect predictions.
            <br />
            Points above = Model overestimates damage.
            <br />
            Points below = Model underestimates damage (misses potholes).
          </div>
        </div>

        {/* Worst Offenders List */}
        <div className="flex-1 bg-[#222] p-4 rounded-lg border border-[#333] overflow-hidden flex flex-col">
          <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <List size={16} />
            Worst Discrepancies
          </h3>
          <div className="overflow-y-auto flex-1">
            <table className="w-full text-sm text-left">
              <thead className="text-xs text-gray-500 uppercase bg-[#1a1a1a] sticky top-0">
                <tr>
                  <th className="px-3 py-2">Img</th>
                  <th className="px-3 py-2">ID</th>
                  <th className="px-3 py-2 text-right">Manual</th>
                  <th className="px-3 py-2 text-right">Model</th>
                  <th className="px-3 py-2 text-right">Diff</th>
                </tr>
              </thead>
              <tbody>
                {worstOffenders.map(p => {
                  const diff = (p.rqiScore || 0) - (p.manualRqi || 0)
                  return (
                    <tr
                      key={p.id}
                      className="border-b border-[#333] hover:bg-[#2a2a2a] cursor-pointer transition-colors"
                      onClick={() => onNavigate(p.id)}>
                      <td className="px-3 py-2">
                        <div className="w-10 h-8 rounded bg-gray-800 overflow-hidden border border-gray-700">
                          {p.imageUrl ? (
                            <img
                              src={getImageUrl(p.imageUrl)}
                              className="w-full h-full object-cover"
                            />
                          ) : (
                            <ImageIcon size={12} className="text-gray-600 m-auto mt-2" />
                          )}
                        </div>
                      </td>
                      <td className="px-3 py-2 font-mono text-xs text-gray-400">#{p.id}</td>
                      <td className="px-3 py-2 text-right font-bold text-green-400">
                        {p.manualRqi}
                      </td>
                      <td className="px-3 py-2 text-right text-blue-400">
                        {p.rqiScore?.toFixed(2)}
                      </td>
                      <td
                        className={`px-3 py-2 text-right font-bold ${Math.abs(diff) > 1.0 ? 'text-red-500' : 'text-yellow-500'}`}>
                        {diff > 0 ? '+' : ''}
                        {diff.toFixed(2)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  )
}

export default EvaluationDashboard
