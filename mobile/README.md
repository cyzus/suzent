# Suzent Mobile

Cross-platform React Native (Expo) app for connecting your phone to a Suzent server.

## Features

### Chat UI
Send messages to your Suzent instance and receive streaming responses — the same AI experience from your phone.

### Node Client
Connect the phone as a **Suzent Node** so the agent can invoke phone capabilities:

| Capability | Command | What it does |
|---|---|---|
| Camera | `camera.snap` | Take a photo (front or back camera) |
| Location | `location.get` | Get GPS coordinates |
| Device Info | `device.info` | Model, OS, platform info |

The phone auto-reconnects to the server if the connection drops.

## Getting started

### Prerequisites
- Node.js 18+
- Expo CLI: `npm install -g expo-cli`
- Expo Go app on your phone (for development)
- Suzent server running on your local network

### Install

```bash
cd mobile
npm install
```

### Run

```bash
npm start
```

Scan the QR code with Expo Go.

### Connect

1. Open the app — enter your Suzent server URL (e.g. `http://192.168.1.50:25314`)
2. The app verifies the connection and takes you to the Chat tab
3. Navigate to the **Node** tab to see the node connection status
4. Enable the node toggle — the phone will appear in `suzent node list`

### Use from suzent

Once connected, try asking:

```
Take a photo with my phone
```

```
Where is my phone right now?
```

```
What kind of device am I using?
```

## Building for production

```bash
# iOS
expo build:ios

# Android
expo build:android
```

Or use EAS Build:

```bash
npm install -g eas-cli
eas build --platform all
```

## Architecture

```
App.tsx               Navigation + state root
src/
  screens/
    ConnectScreen     Initial server URL entry
    ChatScreen        Chat UI with SSE streaming
    NodeScreen        Node status & capabilities
    SettingsScreen    Server URL + device name
  services/
    chatApi.ts        REST + SSE client for /chat, /chats
    nodeClient.ts     WebSocket node client (/ws/node)
  hooks/
    useServerUrl.ts   Persistent server URL (AsyncStorage)
    useNodeClient.ts  Node lifecycle management
  components/
    MessageBubble     Chat message rendering
    NodeStatusBadge   Connection status indicator
```
