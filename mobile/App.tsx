import AsyncStorage from '@react-native-async-storage/async-storage';
import { NavigationContainer } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { StatusBar } from 'expo-status-bar';
import React, { useEffect, useState } from 'react';
import { Text } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { ChatScreen } from './src/screens/ChatScreen';
import { ConnectScreen } from './src/screens/ConnectScreen';
import { NodeScreen } from './src/screens/NodeScreen';
import { SettingsScreen } from './src/screens/SettingsScreen';
import { useNodeClient } from './src/hooks/useNodeClient';
import { useServerUrl } from './src/hooks/useServerUrl';

const Tab = createBottomTabNavigator();

const DEVICE_NAME_KEY = 'suzent_device_name';
const CONNECTED_KEY = 'suzent_connected';
const CHAT_ID_KEY = 'suzent_chat_id';
const NODE_ENABLED_KEY = 'suzent_node_enabled';

export default function App() {
  const { url, saveUrl, loaded } = useServerUrl();
  const [connected, setConnected] = useState(false);
  const [chatId, setChatId] = useState<string | null>(null);
  const [deviceName, setDeviceName] = useState('Mobile');
  const [nodeEnabled, setNodeEnabled] = useState(true);

  useEffect(() => {
    if (!loaded) return;
    Promise.all([
      AsyncStorage.getItem(CONNECTED_KEY),
      AsyncStorage.getItem(CHAT_ID_KEY),
      AsyncStorage.getItem(DEVICE_NAME_KEY),
      AsyncStorage.getItem(NODE_ENABLED_KEY),
    ]).then(([c, cid, dn, ne]) => {
      if (c === '1') setConnected(true);
      if (cid) setChatId(cid);
      if (dn) setDeviceName(dn);
      if (ne === '0') setNodeEnabled(false);
    });
  }, [loaded]);

  const handleConnect = async (newUrl: string) => {
    await saveUrl(newUrl);
    await AsyncStorage.setItem(CONNECTED_KEY, '1');
    setConnected(true);
  };

  const handleDisconnect = async () => {
    await AsyncStorage.multiRemove([CONNECTED_KEY, CHAT_ID_KEY]);
    setConnected(false);
    setChatId(null);
  };

  const handleChatIdChange = async (id: string) => {
    setChatId(id);
    await AsyncStorage.setItem(CHAT_ID_KEY, id);
  };

  const handleSaveDeviceName = async (name: string) => {
    setDeviceName(name);
    await AsyncStorage.setItem(DEVICE_NAME_KEY, name);
  };

  const handleToggleNode = async (val: boolean) => {
    setNodeEnabled(val);
    await AsyncStorage.setItem(NODE_ENABLED_KEY, val ? '1' : '0');
  };

  const nodeClientHook = useNodeClient(url, deviceName, connected && nodeEnabled);

  if (!loaded) return null;

  if (!connected) {
    return (
      <SafeAreaProvider>
        <StatusBar style="light" />
        <ConnectScreen currentUrl={url} onSave={handleConnect} />
      </SafeAreaProvider>
    );
  }

  return (
    <SafeAreaProvider>
      <StatusBar style="light" />
      <NavigationContainer
        theme={{
          dark: true,
          colors: {
            primary: '#6366f1',
            background: '#0a0a0a',
            card: '#0f0f0f',
            text: '#f3f4f6',
            border: '#1f2937',
            notification: '#6366f1',
          },
        }}
      >
        <Tab.Navigator
          screenOptions={{
            tabBarStyle: {
              backgroundColor: '#0f0f0f',
              borderTopColor: '#1f2937',
              borderTopWidth: 1,
            },
            tabBarActiveTintColor: '#6366f1',
            tabBarInactiveTintColor: '#4b5563',
            tabBarLabelStyle: {
              fontSize: 10,
              fontWeight: '700',
              letterSpacing: 0.5,
            },
            headerStyle: { backgroundColor: '#0f0f0f' },
            headerTitleStyle: { color: '#f3f4f6', fontWeight: '800', letterSpacing: 2 },
            headerShadowVisible: false,
          }}
        >
          <Tab.Screen
            name="Chat"
            options={{
              title: 'CHAT',
              tabBarIcon: ({ color }) => <Text style={{ color, fontSize: 18 }}>💬</Text>,
              headerTitle: 'SUZENT',
            }}
          >
            {() => <ChatScreen chatId={chatId} onChatIdChange={handleChatIdChange} />}
          </Tab.Screen>

          <Tab.Screen
            name="Node"
            options={{
              title: 'NODE',
              tabBarIcon: ({ color }) => <Text style={{ color, fontSize: 18 }}>📡</Text>,
              tabBarBadge: nodeClientHook.status === 'connected' ? undefined : '!',
              tabBarBadgeStyle: { backgroundColor: '#ef4444', fontSize: 8 },
            }}
          >
            {() => (
              <NodeScreen
                status={nodeClientHook.status}
                nodeId={nodeClientHook.nodeId}
                nodeEnabled={nodeEnabled}
                onToggleEnabled={handleToggleNode}
                onReconnect={nodeClientHook.reconnect}
              />
            )}
          </Tab.Screen>

          <Tab.Screen
            name="Settings"
            options={{
              title: 'SETTINGS',
              tabBarIcon: ({ color }) => <Text style={{ color, fontSize: 18 }}>⚙️</Text>,
            }}
          >
            {() => (
              <SettingsScreen
                serverUrl={url}
                deviceName={deviceName}
                onSaveUrl={handleConnect}
                onSaveDeviceName={handleSaveDeviceName}
                onDisconnect={handleDisconnect}
              />
            )}
          </Tab.Screen>
        </Tab.Navigator>
      </NavigationContainer>
    </SafeAreaProvider>
  );
}
