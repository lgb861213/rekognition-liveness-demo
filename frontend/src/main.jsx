import React from 'react';
import ReactDOM from 'react-dom/client';
import { ThemeProvider } from '@aws-amplify/ui-react';
import '@aws-amplify/ui-react/styles.css';
import App from './App.jsx';
import { configureAmplify } from './amplifyConfig.js';

configureAmplify();

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ThemeProvider>
      <App />
    </ThemeProvider>
  </React.StrictMode>
);
