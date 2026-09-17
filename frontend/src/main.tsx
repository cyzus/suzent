import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import { WebShell } from './shells/WebShell';
import './styles.css';
import './robot-animations.css';
import { ThemeProvider } from './hooks/useTheme';
import { I18nProvider } from './i18n';
import { captureAuthTokenFromUrl, installAuthenticatedFetch } from './lib/authToken';
import { isWeb } from './lib/runtime';

// Before anything renders or fetches: a remote browser arrives carrying its
// token on the URL, and every request from here on has to be able to use it.
captureAuthTokenFromUrl();
installAuthenticatedFetch();

createRoot(document.getElementById('root')!).render(
  <ThemeProvider>
    <I18nProvider>
      {/* Two shells, one build. The desktop window is a chat app; a browser is
          reaching a headless host, and gets the console that puts the
          operational surfaces on equal footing with chat. */}
      {isWeb() ? <WebShell /> : <App />}
    </I18nProvider>
  </ThemeProvider>
);
