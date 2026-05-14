import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './styles.css';
import './robot-animations.css';
import { ThemeProvider } from './hooks/useTheme';

createRoot(document.getElementById('root')!).render(
  <ThemeProvider>
    <App />
  </ThemeProvider>
);
