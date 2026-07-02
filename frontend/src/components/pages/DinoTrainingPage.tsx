import React, { useCallback } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { DinoTrainingView, useTraining } from 'modules/training'
import { ROUTES, buildPath } from '../../routes'
import { PAGE_SIZE } from '../../constants'

const DinoTrainingPage: React.FC = () => {
  const navigate = useNavigate()
  const { id } = useParams<{ id: string }>()
  const {
    offset,
  } = useTraining()

  const handleNext = useCallback((nextId: string | number) => {
    navigate(buildPath(ROUTES.TRAINING_DINO_REVIEW, { id: String(nextId) }))
  }, [navigate])

  const handlePrev = useCallback((prevId: string | number) => {
    navigate(buildPath(ROUTES.TRAINING_DINO_REVIEW, { id: String(prevId) }))
  }, [navigate])

  const handleClose = useCallback(() => {
    const page = Math.floor(offset / PAGE_SIZE) + 1
    navigate(`${ROUTES.TRAINING_DINO_LIST.path}?page=${page}`)
  }, [navigate, offset])

  return (
    <DinoTrainingView 
      key={id}
      onNext={handleNext} 
      onPrev={handlePrev} 
      onClose={handleClose} 
    />
  )
}

export default DinoTrainingPage
