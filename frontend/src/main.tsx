import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './styles.css';
import './robot-animations.css';
import { ThemeProvider } from './hooks/useTheme';
import { I18nProvider } from './i18n';
import { captureAuthTokenFromUrl, installAuthenticatedFetch } from './lib/authToken';

// Before anything renders or fetches: a remote browser arrives carrying its
// token on the URL, and every request from here on has to be able to use it.
captureAuthTokenFromUrl();
installAuthenticatedFetch();

createRoot(document.getElementById('root')!).render(
  <ThemeProvider>
    <I18nProvider>
      <App />
    </I18nProvider>
  </ThemeProvider>
);
