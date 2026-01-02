import React, { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { useDispatch } from 'react-redux'
import { locationChange } from '../actions'

const LocationListener: React.FC = () => {
  const location = useLocation()
  const dispatch = useDispatch()

  useEffect(() => {
    // Pick only serializable properties to avoid breaking Redux DevTools bridge
    const { pathname, search, hash, state, key } = location
    dispatch(locationChange({ pathname, search, hash, state, key }))
  }, [location, dispatch])

  return null
}

export default LocationListener
