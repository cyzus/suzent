import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { NodeStatus } from '../types';

const STATUS_COLOR: Record<NodeStatus, string> = {
  connected: '#22c55e',
  connecting: '#f59e0b',
  disconnected: '#6b7280',
  error: '#ef4444',
};

const STATUS_LABEL: Record<NodeStatus, string> = {
  connected: 'NODE ONLINE',
  connecting: 'CONNECTING…',
  disconnected: 'NODE OFFLINE',
  error: 'ERROR',
};

export function NodeStatusBadge({ status }: { status: NodeStatus }) {
  const color = STATUS_COLOR[status];
  return (
    <View style={[styles.badge, { borderColor: color }]}>
      <View style={[styles.dot, { backgroundColor: color }]} />
      <Text style={[styles.label, { color }]}>{STATUS_LABEL[status]}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1.5,
    borderRadius: 6,
    paddingHorizontal: 8,
    paddingVertical: 4,
    gap: 6,
  },
  dot: {
    width: 7,
    height: 7,
    borderRadius: 4,
  },
  label: {
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 0.8,
  },
});
