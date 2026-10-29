import { useCallback, useEffect, useState } from 'react';

const DETAIL_KEY = 'suzentMobileDetail';

/** Keep the mounted conversation alive while the mobile list is visible. */
export function useMobileNavigation(mobile: boolean): {
  detail: boolean;
  open: () => void;
  back: () => void;
} {
  const [detail, setDetail] = useState(() => Boolean(window.history.state?.[DETAIL_KEY]));

  useEffect(() => {
    const onPopState = (): void => setDetail(Boolean(window.history.state?.[DETAIL_KEY]));
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  const open = useCallback((): void => {
    if (!mobile) return;
    if (!window.history.state?.[DETAIL_KEY]) {
      window.history.pushState({ ...window.history.state, [DETAIL_KEY]: true }, '');
    }
    setDetail(true);
  }, [mobile]);

  const back = useCallback((): void => {
    if (window.history.state?.[DETAIL_KEY]) window.history.back();
    else setDetail(false);
  }, []);

  return { detail, open, back };
}
