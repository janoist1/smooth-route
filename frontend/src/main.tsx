import React from 'react'
import ReactDOM from 'react-dom/client'
import { Provider } from 'react-redux'
import { store } from './store'
import App from './components/App'
import './index.css'

const strictMode = false // TODO: use strict mode in some configurations
const Fragment = strictMode ? React.StrictMode : React.Fragment

ReactDOM.createRoot(document.getElementById('root')!).render(
  <Fragment>
    <Provider store={store}>
      <App />
    </Provider>
  </Fragment>,
)
