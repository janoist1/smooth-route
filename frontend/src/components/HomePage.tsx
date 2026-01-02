import React from 'react'
import MapView from '../modules/map/components/MapView'
import MapLegend from '../modules/map/components/MapLegend'

const HomePage: React.FC = () => {
  return (
    <>
      <main>
        <MapView />
      </main>
      <MapLegend />
    </>
  )
}

export default HomePage
