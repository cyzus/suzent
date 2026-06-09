import React from 'react';
import { Platform, ScrollView, StyleSheet, Switch, Text, TouchableOpacity, View } from 'react-native';
import { NodeStatusBadge } from '../components/NodeStatusBadge';
import { CAPABILITIES } from '../services/nodeClient';
import { NodeStatus } from '../types';

interface Props {
  status: NodeStatus;
  nodeId: string | null;
  nodeEnabled: boolean;
  onToggleEnabled: (val: boolean) => void;
  onReconnect: () => void;
}

export function NodeScreen({ status, nodeId, nodeEnabled, onToggleEnabled, onReconnect }: Props) {
  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <View style={styles.header}>
        <View style={styles.titleRow}>
          <Text style={styles.title}>NODE</Text>
          <NodeStatusBadge status={status} />
        </View>
        <Text style={styles.subtitle}>
          Connect this device as a Suzent node so the agent can invoke its capabilities.
        </Text>
      </View>

      <View style={styles.card}>
        <View style={styles.row}>
          <View style={styles.rowLabel}>
            <Text style={styles.fieldLabel}>NODE ACTIVE</Text>
            <Text style={styles.fieldHint}>Advertise this device to suzent</Text>
          </View>
          <Switch
            value={nodeEnabled}
            onValueChange={onToggleEnabled}
            trackColor={{ false: '#1f2937', true: '#4338ca' }}
            thumbColor={nodeEnabled ? '#6366f1' : '#6b7280'}
          />
        </View>

        {nodeId && (
          <View style={styles.divider}>
            <Text style={styles.fieldLabel}>NODE ID</Text>
            <Text style={styles.nodeId} selectable>{nodeId}</Text>
          </View>
        )}
      </View>

      <Text style={styles.sectionTitle}>CAPABILITIES</Text>
      <View style={styles.card}>
        {CAPABILITIES.map((cap, i) => (
          <View key={cap.name}>
            {i > 0 && <View style={styles.separator} />}
            <View style={styles.capRow}>
              <Text style={styles.capName}>{cap.name}</Text>
              <Text style={styles.capDesc}>{cap.description}</Text>
              {Object.keys(cap.params_schema).length > 0 && (
                <Text style={styles.capSchema}>
                  params: {Object.entries(cap.params_schema).map(([k, v]) => `${k}: ${v}`).join(', ')}
                </Text>
              )}
            </View>
          </View>
        ))}
      </View>

      <Text style={styles.sectionTitle}>HOW TO USE</Text>
      <View style={styles.card}>
        <Text style={styles.howToText}>
          Once connected, ask suzent:{'\n\n'}
          <Text style={styles.codeText}>
            "Take a photo with my phone"{'\n'}
            "Where is my phone right now?"{'\n'}
            "What device am I using?"
          </Text>
          {'\n\n'}
          The agent will invoke the corresponding capability on this device.
        </Text>
      </View>

      {status === 'error' || status === 'disconnected' ? (
        <TouchableOpacity
          style={styles.reconnectBtn}
          onPress={onReconnect}
          activeOpacity={0.8}
        >
          <Text style={styles.reconnectText}>RECONNECT</Text>
        </TouchableOpacity>
      ) : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0a0a0a',
  },
  content: {
    padding: 16,
    gap: 16,
  },
  header: {
    gap: 8,
  },
  titleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  title: {
    color: '#f3f4f6',
    fontSize: 22,
    fontWeight: '900',
    letterSpacing: 4,
  },
  subtitle: {
    color: '#6b7280',
    fontSize: 13,
    lineHeight: 20,
  },
  card: {
    backgroundColor: '#111827',
    borderWidth: 1.5,
    borderColor: '#1f2937',
    borderRadius: 12,
    overflow: 'hidden',
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 16,
  },
  rowLabel: {
    flex: 1,
    gap: 2,
  },
  divider: {
    borderTopWidth: 1,
    borderTopColor: '#1f2937',
    padding: 16,
    gap: 6,
  },
  fieldLabel: {
    color: '#9ca3af',
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 1.5,
  },
  fieldHint: {
    color: '#4b5563',
    fontSize: 12,
  },
  nodeId: {
    color: '#6366f1',
    fontSize: 12,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
  },
  sectionTitle: {
    color: '#6b7280',
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 2,
    marginBottom: -8,
  },
  separator: {
    height: 1,
    backgroundColor: '#1f2937',
    marginHorizontal: 16,
  },
  capRow: {
    padding: 14,
    gap: 4,
  },
  capName: {
    color: '#a5b4fc',
    fontSize: 13,
    fontWeight: '700',
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
  },
  capDesc: {
    color: '#9ca3af',
    fontSize: 13,
  },
  capSchema: {
    color: '#4b5563',
    fontSize: 11,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
  },
  howToText: {
    color: '#9ca3af',
    fontSize: 13,
    lineHeight: 20,
    padding: 16,
  },
  codeText: {
    color: '#a5b4fc',
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
    fontSize: 12,
  },
  reconnectBtn: {
    backgroundColor: '#1f2937',
    borderWidth: 2,
    borderColor: '#374151',
    borderRadius: 10,
    paddingVertical: 14,
    alignItems: 'center',
  },
  reconnectText: {
    color: '#9ca3af',
    fontSize: 12,
    fontWeight: '800',
    letterSpacing: 2,
  },
});
