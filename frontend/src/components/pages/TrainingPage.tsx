import React, { useCallback } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useSelector } from 'react-redux'
import { TrainingView, selectors as trainingSelectors } from 'modules/training'
import type { TrainingState } from 'modules/training'
import { PAGE_SIZE } from '../../constants'

interface TrainingLocationState {
  allIds?: (string | number)[]
}

const TrainingPage: React.FC = () => {
  const navigate = useNavigate()
  const location = useLocation()

  const navIdsFromRedux = useSelector(
    (state: { training: TrainingState }) => state.training.navigationIds,
  )
  const activeMode = useSelector(trainingSelectors.selectActiveMode)
  const offset = useSelector(trainingSelectors.selectOffset)

  const allIds = React.useMemo(() => {
    if (navIdsFromRedux && navIdsFromRedux.length > 0) return navIdsFromRedux
    return (location.state as TrainingLocationState)?.allIds || []
  }, [navIdsFromRedux, location.state])

  const handleNext = useCallback(
    (nextId: string | number) => {
      navigate(`/training/${nextId}/review`, { state: { allIds } })
    },
    [navigate, allIds],
  )

  const handlePrev = useCallback(
    (prevId: string | number) => {
      navigate(`/training/${prevId}/review`, { state: { allIds } })
    },
    [navigate, allIds],
  )

  const handleClose = useCallback(() => {
    const page = Math.floor(offset / PAGE_SIZE) + 1
    navigate(`/training?mode=${activeMode}&page=${page}`)
  }, [navigate, activeMode, offset])

  return (
    <TrainingView allIds={allIds} onNext={handleNext} onPrev={handlePrev} onClose={handleClose} />
  )
}

export default TrainingPage
