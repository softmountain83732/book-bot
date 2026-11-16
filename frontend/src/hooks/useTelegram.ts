// frontend/src/hooks/useTelegram.ts
import { useEffect, useState } from 'react';

export function useTelegram() {
  const [isReady, setIsReady] = useState(false);
  const [colorScheme, setColorScheme] = useState<'light' | 'dark'>('light');

  useEffect(() => {
    const tg = window.Telegram?.WebApp;

    const applyTheme = () => {
      if (!tg) return;
      const scheme = tg.colorScheme || 'light';
      setColorScheme(scheme);
      document.body.setAttribute('data-theme', scheme);
      if (scheme === 'dark') {
        document.body.classList.add('dark');
      } else {
        document.body.classList.remove('dark');
      }

      // If Telegram provides specific theme parameters, inject them into CSS root
      const params = tg.themeParams;
      if (params) {
        const root = document.documentElement;
        if (params.bg_color) root.style.setProperty('--tg-theme-bg-color', params.bg_color);
        if (params.text_color) root.style.setProperty('--tg-theme-text-color', params.text_color);
        if (params.hint_color) root.style.setProperty('--tg-theme-hint-color', params.hint_color);
        if (params.link_color) root.style.setProperty('--tg-theme-link-color', params.link_color);
        if (params.button_color) root.style.setProperty('--tg-theme-button-color', params.button_color);
        if (params.button_text_color) root.style.setProperty('--tg-theme-button-text-color', params.button_text_color);
        if (params.secondary_bg_color) root.style.setProperty('--tg-theme-secondary-bg-color', params.secondary_bg_color);
        if (params.header_bg_color) root.style.setProperty('--tg-theme-header-bg-color', params.header_bg_color);
      }
    };

    if (tg) {
      tg.ready();
      tg.expand();
      setIsReady(true);
      applyTheme();

      // Listen for runtime theme changes
      tg.onEvent('themeChanged', applyTheme);

      return () => {
        tg.offEvent('themeChanged', applyTheme);
      };
    } else {
      // Browser fallback
      setIsReady(true);
    }
  }, []);

  const triggerHaptic = (style: 'light' | 'medium' | 'heavy' = 'light') => {
    try {
      window.Telegram?.WebApp?.HapticFeedback?.impactOccurred(style);
    } catch {
      // Ignore if not supported in environment
    }
  };

  const triggerSuccess = () => {
    try {
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred('success');
    } catch {
      // Ignore
    }
  };

  const triggerError = () => {
    try {
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred('error');
    } catch {
      // Ignore
    }
  };

  return {
    tg: window.Telegram?.WebApp,
    user: window.Telegram?.WebApp?.initDataUnsafe?.user,
    initData: window.Telegram?.WebApp?.initData || '',
    isReady,
    colorScheme,
    triggerHaptic,
    triggerSuccess,
    triggerError,
  };
}
