import app from './app'
import router from './router'

// Combine all global sagas into a single array
export default [...app, ...router]
