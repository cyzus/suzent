/**
 * Suzent Node WebSocket client.
 *
 * Connects this device to the Suzent server as a controllable Node,
 * advertising capabilities (camera, location, device info) and handling
 * invoke commands dispatched by the agent.
 */

import * as Camera from 'expo-camera';
import * as Device from 'expo-device';
import * as Location from 'expo-location';
import { Platform } from 'react-native';
import { NodeCapability, NodeStatus } from '../types';

type InvokeHandler = (command: string, params: Record<string, unknown>) => Promise<unknown>;

export const CAPABILITIES: NodeCapability[] = [
  {
    name: 'camera.snap',
    description: 'Take a photo with the device camera',
    params_schema: { quality: 'float', facing: 'str' },
  },
  {
    name: 'location.get',
    description: 'Get the current GPS coordinates of the device',
    params_schema: { accuracy: 'str' },
  },
  {
    name: 'device.info',
    description: 'Get device information (model, OS, platform)',
    params_schema: {},
  },
];

export class SuzentNodeClient {
  private ws: WebSocket | null = null;
  private nodeId: string | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private alive = false;

  onStatusChange: (status: NodeStatus) => void = () => {};
  onNodeId: (id: string) => void = () => {};

  private serverUrl = '';
  private displayName = '';

  connect(serverUrl: string, displayName: string) {
    this.serverUrl = serverUrl;
    this.displayName = displayName;
    this.alive = true;
    this._connect();
  }

  disconnect() {
    this.alive = false;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.ws?.close();
    this.ws = null;
    this.nodeId = null;
    this.onStatusChange('disconnected');
  }

  private _connect() {
    if (!this.alive) return;

    const base = this.serverUrl.replace(/^http/, 'ws');
    const wsUrl = `${base}/ws/node`;

    this.onStatusChange('connecting');

    const ws = new WebSocket(wsUrl);
    this.ws = ws;

    ws.onopen = () => {
      ws.send(
        JSON.stringify({
          type: 'connect',
          display_name: this.displayName,
          platform: Platform.OS,
          capabilities: CAPABILITIES,
        })
      );
    };

    ws.onmessage = async (event) => {
      let data: Record<string, unknown>;
      try {
        data = JSON.parse(event.data as string);
      } catch {
        return;
      }

      const msgType = data.type as string;

      if (msgType === 'connected') {
        this.nodeId = data.node_id as string;
        this.onStatusChange('connected');
        this.onNodeId(this.nodeId);
      } else if (msgType === 'ping') {
        ws.send(JSON.stringify({ type: 'pong' }));
      } else if (msgType === 'invoke') {
        const requestId = data.request_id as string;
        const command = data.command as string;
        const params = (data.params as Record<string, unknown>) ?? {};

        try {
          const result = await this._handleInvoke(command, params);
          ws.send(
            JSON.stringify({
              type: 'result',
              request_id: requestId,
              success: true,
              result,
            })
          );
        } catch (err: unknown) {
          ws.send(
            JSON.stringify({
              type: 'result',
              request_id: requestId,
              success: false,
              error: String(err),
            })
          );
        }
      }
    };

    ws.onerror = () => {
      this.onStatusChange('error');
    };

    ws.onclose = () => {
      if (this.alive) {
        this.onStatusChange('disconnected');
        this.reconnectTimer = setTimeout(() => this._connect(), 5000);
      }
    };
  }

  private async _handleInvoke(
    command: string,
    params: Record<string, unknown>
  ): Promise<unknown> {
    switch (command) {
      case 'camera.snap':
        return this._snapCamera(params);
      case 'location.get':
        return this._getLocation(params);
      case 'device.info':
        return this._getDeviceInfo();
      default:
        throw new Error(`Unknown command: ${command}`);
    }
  }

  private async _snapCamera(params: Record<string, unknown>): Promise<unknown> {
    const { status } = await Camera.requestCameraPermissionsAsync();
    if (status !== 'granted') {
      throw new Error('Camera permission not granted');
    }

    // Use ImagePicker as a lightweight alternative to CameraView for node invocation
    const ImagePicker = await import('expo-image-picker');
    const facing = params.facing === 'front' ? ImagePicker.CameraType.front : ImagePicker.CameraType.back;
    const result = await ImagePicker.launchCameraAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: typeof params.quality === 'number' ? params.quality : 0.8,
      cameraType: facing,
      base64: true,
    });

    if (result.canceled || !result.assets?.length) {
      throw new Error('Camera capture cancelled');
    }

    const asset = result.assets[0];
    return {
      uri: asset.uri,
      width: asset.width,
      height: asset.height,
      base64: asset.base64 ?? null,
    };
  }

  private async _getLocation(params: Record<string, unknown>): Promise<unknown> {
    const { status } = await Location.requestForegroundPermissionsAsync();
    if (status !== 'granted') {
      throw new Error('Location permission not granted');
    }

    const accuracy =
      params.accuracy === 'high'
        ? Location.Accuracy.High
        : Location.Accuracy.Balanced;

    const loc = await Location.getCurrentPositionAsync({ accuracy });
    return {
      latitude: loc.coords.latitude,
      longitude: loc.coords.longitude,
      accuracy: loc.coords.accuracy,
      altitude: loc.coords.altitude,
      timestamp: loc.timestamp,
    };
  }

  private async _getDeviceInfo(): Promise<unknown> {
    return {
      brand: Device.brand,
      model: Device.modelName,
      os: Platform.OS,
      os_version: Platform.Version,
      device_type: Device.deviceType,
      is_device: Device.isDevice,
    };
  }
}

export const nodeClient = new SuzentNodeClient();
