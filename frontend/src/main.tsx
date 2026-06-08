import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './styles.css';
import './robot-animations.css';
import { ThemeProvider } from './hooks/useTheme';
import { I18nProvider } from './i18n';

createRoot(document.getElementById('root')!).render(
  <ThemeProvider>
    <I18nProvider>
      <App />
    </I18nProvider>
  </ThemeProvider>
);
