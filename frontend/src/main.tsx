import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './styles.css';
import './robot-animations.css';
import { I18nProvider } from './i18n';
import { ThemeProvider } from './hooks/useTheme';

createRoot(document.getElementById('root')!).render(
  <I18nProvider>
    <ThemeProvider>
      <App />
    </ThemeProvider>
  </I18nProvider>
);
