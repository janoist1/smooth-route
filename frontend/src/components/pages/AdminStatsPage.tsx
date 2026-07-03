import React from 'react'
import { gql } from '@apollo/client'
import { useQuery } from '@apollo/client/react'
import { Loader2, ImageIcon, DollarSign, MapPin, Users } from 'lucide-react'
import { StatCard, StatsGrid } from 'modules/ui'
import MainLayout from '../MainLayout'

const ADMIN_STATS_QUERY = gql`
  query AdminStats {
    adminStats {
      totalImages
      imagesThisMonth
      freeTierLimit
      billableThisMonth
      totalPoints
      analyzedPoints
      pendingAnalysis
      rqiGood
      rqiFair
      rqiPoor
      totalUsers
      adminUsers
      imagesPerDay {
        day
        count
      }
      recentJobs {
        id
        status
        message
        progress
        total
      }
    }
  }
`

interface DailyCount {
  day: string
  count: number
}
interface JobSummary {
  id: string
  status: string
  message: string | null
  progress: number
  total: number
}
interface AdminStats {
  totalImages: number
  imagesThisMonth: number
  freeTierLimit: number
  billableThisMonth: number
  totalPoints: number
  analyzedPoints: number
  pendingAnalysis: number
  rqiGood: number
  rqiFair: number
  rqiPoor: number
  totalUsers: number
  adminUsers: number
  imagesPerDay: DailyCount[]
  recentJobs: JobSummary[]
}

// Street View Static overage price (Essentials SKU, ~$7 / 1000 requests).
const PRICE_PER_IMAGE = 0.007

const card = {
  background: 'rgba(255,255,255,0.05)',
  border: '1px solid rgba(255,255,255,0.1)',
  borderRadius: 16,
  padding: 20,
}

const StatusDot: React.FC<{ status: string }> = ({ status }) => {
  const color =
    status === 'completed'
      ? '#34d399'
      : status === 'failed'
        ? '#f87171'
        : status === 'cancelled'
          ? '#9ca3af'
          : '#facc15'
  return (
    <span style={{ color, marginRight: 6 }}>●</span>
  )
}

const AdminStatsPage: React.FC = () => {
  const { data, loading, error } = useQuery<{ adminStats: AdminStats }>(ADMIN_STATS_QUERY, {
    fetchPolicy: 'no-cache',
  })

  if (loading && !data) {
    return (
      <MainLayout>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', background: '#111' }}>
          <Loader2 className="admin-spin" size={40} color="#3b82f6" />
          <style>{`.admin-spin{animation:aspin 1s linear infinite}@keyframes aspin{100%{transform:rotate(360deg)}}`}</style>
        </div>
      </MainLayout>
    )
  }

  if (error || !data) {
    return (
      <MainLayout>
        <div style={{ padding: 40, color: '#f87171', background: '#111', minHeight: '100vh' }}>
          Hiba a statisztika betöltésekor: {error?.message ?? 'ismeretlen hiba'}
        </div>
      </MainLayout>
    )
  }

  const s = data.adminStats
  const usedPct = Math.min(100, (s.imagesThisMonth / s.freeTierLimit) * 100)
  const estCost = s.billableThisMonth * PRICE_PER_IMAGE
  const overFree = s.imagesThisMonth >= s.freeTierLimit
  const maxDay = Math.max(1, ...s.imagesPerDay.map(d => d.count))
  const rqiTotal = Math.max(1, s.rqiGood + s.rqiFair + s.rqiPoor)

  return (
    <MainLayout>
      <div style={{ background: '#111', minHeight: '100vh', color: 'white', padding: '32px', overflowY: 'auto' }}>
        <div style={{ maxWidth: 1100, margin: '0 auto' }}>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 700, marginBottom: 4 }}>Admin — statisztika &amp; monitoring</h1>
          <p style={{ color: '#9ca3af', marginBottom: 28 }}>
            Használat, lefedettség és jobok. A képszám a Google Street View Static költség közelítése
            (1 tárolt kép ≈ 1 számlázható kérés; a keret havonta nullázódik).
          </p>

          <StatsGrid>
            <StatCard
              label="Google usage (hó)"
              value={`${s.imagesThisMonth.toLocaleString()} / ${s.freeTierLimit.toLocaleString()}`}
              theme={overFree ? 'red' : 'green'}
              icon={<ImageIcon size={16} />}
              subtext={overFree ? 'ingyenkeret túllépve' : 'ingyenkereten belül'}
            />
            <StatCard
              label="Becsült költség (hó)"
              value={estCost > 0 ? `~$${estCost.toFixed(2)}` : '$0'}
              theme={estCost > 0 ? 'yellow' : 'green'}
              icon={<DollarSign size={16} />}
              subtext={`${s.billableThisMonth.toLocaleString()} számlázható kép`}
            />
            <StatCard
              label="Összes kép"
              value={s.totalImages.toLocaleString()}
              theme="blue"
              icon={<MapPin size={16} />}
              subtext={`${s.pendingAnalysis} elemzésre vár`}
            />
            <StatCard
              label="Felhasználók"
              value={s.totalUsers}
              theme="neutral"
              icon={<Users size={16} />}
              subtext={`${s.adminUsers} admin`}
            />
          </StatsGrid>

          {/* Free-tier usage bar */}
          <div style={{ ...card, marginBottom: 24 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', color: '#9ca3af', marginBottom: 8 }}>
              <span>Havi ingyenkeret felhasználva</span>
              <span>{Math.round(usedPct)}%</span>
            </div>
            <div style={{ height: 12, borderRadius: 6, background: 'rgba(255,255,255,0.08)', overflow: 'hidden' }}>
              <div style={{ height: '100%', width: `${usedPct}%`, background: overFree ? '#ef4444' : usedPct > 80 ? '#facc15' : '#34d399', transition: 'width .3s' }} />
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, marginBottom: 24 }}>
            {/* Images per day */}
            <div style={card}>
              <h3 style={{ fontSize: '1rem', marginBottom: 16 }}>Új képek / nap (utolsó 14 nap)</h3>
              <div style={{ display: 'flex', alignItems: 'flex-end', gap: 6, height: 120 }}>
                {s.imagesPerDay.length === 0 && <span style={{ color: '#6b7280' }}>Nincs adat.</span>}
                {s.imagesPerDay.map(d => (
                  <div key={d.day} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }} title={`${d.day}: ${d.count}`}>
                    <div style={{ width: '100%', height: `${(d.count / maxDay) * 100}%`, minHeight: 2, background: '#60a5fa', borderRadius: '3px 3px 0 0' }} />
                    <span style={{ fontSize: '0.6rem', color: '#6b7280' }}>{d.day.slice(5)}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* RQI distribution */}
            <div style={card}>
              <h3 style={{ fontSize: '1rem', marginBottom: 16 }}>Útminőség-eloszlás</h3>
              {([
                ['Jó (RQI ≤ 2)', s.rqiGood, '#34d399'],
                ['Közepes (2–3)', s.rqiFair, '#facc15'],
                ['Rossz (> 3)', s.rqiPoor, '#f87171'],
              ] as const).map(([label, count, color]) => (
                <div key={label} style={{ marginBottom: 12 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', marginBottom: 4 }}>
                    <span>{label}</span>
                    <span style={{ color: '#9ca3af' }}>{count.toLocaleString()} ({Math.round((count / rqiTotal) * 100)}%)</span>
                  </div>
                  <div style={{ height: 8, borderRadius: 4, background: 'rgba(255,255,255,0.08)', overflow: 'hidden' }}>
                    <div style={{ height: '100%', width: `${(count / rqiTotal) * 100}%`, background: color }} />
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Recent jobs */}
          <div style={card}>
            <h3 style={{ fontSize: '1rem', marginBottom: 16 }}>Legutóbbi jobok</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {s.recentJobs.length === 0 && <span style={{ color: '#6b7280' }}>Nincs job.</span>}
              {s.recentJobs.map(j => (
                <div key={j.id} style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: '0.85rem', borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: 6 }}>
                  <span style={{ width: 90, color: '#9ca3af', fontFamily: 'monospace' }}>{j.id.slice(0, 8)}</span>
                  <span style={{ width: 110 }}><StatusDot status={j.status} />{j.status}</span>
                  <span style={{ flex: 1, color: '#d1d5db', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{j.message}</span>
                  <span style={{ color: '#6b7280' }}>{j.total > 0 ? `${j.progress}%` : ''}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </MainLayout>
  )
}

export default AdminStatsPage
