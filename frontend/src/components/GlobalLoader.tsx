import React from 'react'
import { useSelector } from 'react-redux'
import type { RootState } from '../store'
import { TopProgressBar } from 'modules/ui'

const GlobalLoader: React.FC = () => {
  // Aggregate loading states from all modules
  const isLoading = useSelector((state: RootState) => {
    return (
      state.training.loading || state.map.loading
      // Add other module loading states here
    )
  })

  return <TopProgressBar isLoading={isLoading} />
}

export default GlobalLoader
