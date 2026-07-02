import React from 'react'
import type { TrainingStats as StatsType } from '../types'
import { StatsGrid, StatCard } from '../../ui'
import { BarChart2, Clock, CheckCircle, AlertCircle } from 'lucide-react'

interface Props {
  stats: StatsType | null
}

export const DinoTrainingStats: React.FC<Props> = ({ stats }) => {
  if (!stats) return null

  return (
    <StatsGrid>
      <StatCard
        label="Összes"
        value={stats.total}
        icon={<BarChart2 size={16} />}
        theme="neutral"
      />
      <StatCard
        label="Pending"
        value={stats.pending}
        icon={<Clock size={16} />}
        theme="blue"
      />
      <StatCard
        label="RQI 1"
        value={stats.rqi1Count}
        icon={<CheckCircle size={16} />}
        theme="green"
      />
      <StatCard
        label="RQI 2"
        value={stats.rqi2Count}
        icon={<CheckCircle size={16} />}
        theme="green"
      />
      <StatCard
        label="RQI 3"
        value={stats.rqi3Count}
        icon={<AlertCircle size={16} />}
        theme="yellow"
      />
      <StatCard
        label="RQI 4"
        value={stats.rqi4Count}
        icon={<AlertCircle size={16} />}
        theme="yellow"
      />
      <StatCard
        label="RQI 5"
        value={stats.rqi5Count}
        icon={<AlertCircle size={16} />}
        theme="red"
      />
    </StatsGrid>
  )
}
