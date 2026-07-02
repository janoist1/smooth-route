import React from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { MapView, MapLegend } from 'modules/map'
import MainLayout from './MainLayout'
import { useRqiDisplaySource } from 'modules/settings'

const HomePage: React.FC = () => {
  const navigate = useNavigate()
  const [, setSearchParams] = useSearchParams()

  const displaySource = useRqiDisplaySource()

  const handleTrain = (id: string | number, model?: 'yolo' | 'dino') => {
    // Priority: Explicit argument > Setting > Default
    const target = model || (displaySource === 'dino' ? 'dino' : 'yolo')
    
    if (target === 'dino') {
        navigate(`/training/dino/${id}/review`)
    } else {
        navigate(`/training/${id}`)
    }
  }

  const handleMapMove = React.useCallback(
    (_bbox: number[], center: [number, number], zoom: number) => {
      setSearchParams(
        prev => {
          const next = new URLSearchParams(prev)
          next.set('lat', center[0].toFixed(6))
          next.set('lng', center[1].toFixed(6))
          next.set('z', zoom.toString())
          return next
        },
        { replace: true },
      )
    },
    [setSearchParams],
  )

  return (
    <MainLayout>
      <main>
        <MapView onTrain={handleTrain} onMapMove={handleMapMove} />
      </main>
      <MapLegend />
    </MainLayout>
  )
}

export default HomePage
