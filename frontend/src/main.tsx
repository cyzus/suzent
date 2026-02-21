import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './styles.css';
import './robot-animations.css';
import { I18nProvider } from './i18n';

createRoot(document.getElementById('root')!).render(
  <I18nProvider>
    <App />
  </I18nProvider>
);
