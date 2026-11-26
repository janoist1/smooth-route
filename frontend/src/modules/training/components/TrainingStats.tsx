import React from 'react'
import { BarChart2, AlertTriangle, Check, List as ListIcon } from 'lucide-react'
import { StatsGrid, StatCard, atOrBetter, rqiLevel, rqiValue } from '../../ui'

// Average-RQI card theme on the canonical scale: green up to Jó, yellow up to
// the Közepes|Rossz midpoint, red beyond (the trainingStats buckets).
const GOOD = rqiValue('good')
const FAIR_POOR = (rqiValue('fair') + rqiValue('poor')) / 2

interface StatsProps {
  stats: {
    total: number
    reviewNeeded: number
    annotated: number
    avgRqi: string | number
    good: number
    fair: number
    poor: number
  } | null
}

const TrainingStats: React.FC<StatsProps> = ({ stats }) => {
  if (!stats) return null

  const getRqiTheme = (score: string | number) => {
    const num = typeof score === 'string' ? parseFloat(score) : score
    if (!Number.isFinite(num) || num <= 0) return 'neutral' // no scored points
    if (atOrBetter(num, GOOD)) return 'green'
    if (atOrBetter(num, FAIR_POOR)) return 'yellow'
    return 'red'
  }

  return (
    <StatsGrid>
      <StatCard
        label="Points in View"
        value={stats.total}
        subtext="Matching current filter"
        icon={<ListIcon size={16} />}
        theme="neutral"
      />

      <StatCard
        label="Annotated"
        value={stats.annotated}
        subtext={`${((stats.annotated / stats.total) * 100).toFixed(1)}% complete`}
        icon={<Check size={16} />}
        theme="blue"
      />

      <StatCard
        label="Review Needed"
        value={stats.reviewNeeded}
        subtext="Requires attention"
        icon={<AlertTriangle size={16} />}
        theme="yellow"
      />

      <StatCard
        label="Avg Quality"
        value={stats.avgRqi}
        icon={<BarChart2 size={16} />}
        theme={getRqiTheme(stats.avgRqi)}
        subtext={
          <div style={{ display: 'flex', gap: '4px' }}>
            <span style={{ color: rqiLevel(rqiValue('good'))?.color }}>{stats.good} G</span> •
            <span style={{ color: rqiLevel(rqiValue('fair'))?.color }}>{stats.fair} F</span> •
            <span style={{ color: rqiLevel(rqiValue('poor'))?.color }}>{stats.poor} P</span>
          </div>
        }
      />
    </StatsGrid>
  )
}

export default TrainingStats
