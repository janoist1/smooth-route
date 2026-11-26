import React from 'react'
import { useNavigate } from 'react-router-dom'
import { QuickLabelView } from 'modules/labeling'
import { ROUTES } from '../../routes'

// Full-screen on purpose (no floating nav): the screen is built for a phone.
const QuickLabelPage: React.FC = () => {
  const navigate = useNavigate()
  return <QuickLabelView onBack={() => navigate(ROUTES.TRAINING_LIST.path)} />
}

export default QuickLabelPage
