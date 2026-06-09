import AsyncStorage from '@react-native-async-storage/async-storage';
import { useEffect, useState } from 'react';
import { setBaseUrl } from '../services/chatApi';

const KEY = 'suzent_server_url';
const DEFAULT = 'http://192.168.1.100:25314';

export function useServerUrl() {
  const [url, setUrlState] = useState('');
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    AsyncStorage.getItem(KEY).then((v) => {
      const saved = v ?? DEFAULT;
      setUrlState(saved);
      setBaseUrl(saved);
      setLoaded(true);
    });
  }, []);

  const saveUrl = async (newUrl: string) => {
    const clean = newUrl.trim().replace(/\/$/, '');
    await AsyncStorage.setItem(KEY, clean);
    setUrlState(clean);
    setBaseUrl(clean);
  };

  return { url, saveUrl, loaded };
}
