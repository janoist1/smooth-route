import React, { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { useDispatch } from 'react-redux'
import { locationChange } from '../actions'

const LocationListener: React.FC = () => {
  const location = useLocation()
  const dispatch = useDispatch()

  useEffect(() => {
    dispatch(locationChange(location))
  }, [location, dispatch])

  return null
}

export default LocationListener
