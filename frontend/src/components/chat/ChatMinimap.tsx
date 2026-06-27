import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { Message } from '../../types/api';
import { formatMessageTime } from '../../lib/chatUtils';
import { useI18n } from '../../i18n';

type ChatMinimapMessageTone = 'user' | 'assistant' | 'notice' | 'activity';

interface ChatMinimapMarker {
  id: string;
  targetIndex: number;
  relatedIndices: number[];
  tone: ChatMinimapMessageTone;
  title: string;
  snippet: string;
  meta: string[];
}

const MIN_MARKERS_TO_SHOW = 4;
const RAIL_INSET_PERCENT = 4;

interface ChatMinimapProps {
  messages: Message[];
  scrollContainerRef: React.RefObject<HTMLDivElement>;
  onJumpToMessage: (index: number) => void;
}

interface MinimapLabels {
  user: string;
  assistant: string;
  notice: string;
  activity: string;
  files: (count: number) => string;
  images: (count: number) => string;
}

const markerToneClass: Record<ChatMinimapMessageTone, string> = {
  user: 'chat-minimap-marker-user',
  assistant: 'chat-minimap-marker-assistant',
  notice: 'chat-minimap-marker-notice',
  activity: 'chat-minimap-marker-activity',
};

function getMessageTone(message: Message): ChatMinimapMessageTone {
  if (message.role === 'user') return 'user';
  if (message.role === 'assistant') return 'assistant';
  if (message.role === 'notice' || message.role === 'system_triggered') return 'notice';
  return 'activity';
}

function cleanPreviewText(content: string): string {
  return content
    .replace(/<details[\s\S]*?<\/details>/g, ' ')
    .replace(/<div\s+data-a2ui="[^"]*"><\/div>/g, ' ')
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/!\[[^\]]*]\([^)]+\)/g, ' ')
    .replace(/\[([^\]]+)]\([^)]+\)/g, '$1')
    .replace(/[*_`>#-]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function previewTitle(content: string, fallback: string): string {
  const text = cleanPreviewText(content);
  const firstSentence = text.match(/^(.{1,72}?)(?:[.!?]\s|$)/)?.[1]?.trim();
  return firstSentence || fallback;
}

function previewSnippet(content: string, title: string): string {
  const text = cleanPreviewText(content);
  return text && text !== title ? text : '';
}

function buildStandaloneMarker(message: Message, index: number, labels: MinimapLabels): ChatMinimapMarker {
  const tone = getMessageTone(message);
  const fallbackTitle = tone === 'user'
    ? labels.user
    : tone === 'assistant'
      ? labels.assistant
      : tone === 'notice'
        ? labels.notice
        : labels.activity;

  const title = previewTitle(message.content || '', fallbackTitle);
  const snippet = previewSnippet(message.content || '', title);
  const meta = [
    message.timestamp ? formatMessageTime(message.timestamp) : '',
    message.files?.length ? labels.files(message.files.length) : '',
    message.images?.length ? labels.images(message.images.length) : '',
  ].filter(Boolean);

  return {
    id: `message-${index}`,
    targetIndex: index,
    relatedIndices: [index],
    tone,
    title,
    snippet,
    meta,
  };
}

function buildTurnMarker(
  userMessage: Message,
  userIndex: number,
  assistantMessage: Message | null,
  assistantIndex: number | null,
  labels: MinimapLabels,
): ChatMinimapMarker {
  const title = previewTitle(userMessage.content || '', labels.user);
  const assistantSnippet = assistantMessage ? previewSnippet(assistantMessage.content || '', '') : '';
  const userSnippet = previewSnippet(userMessage.content || '', title);
  const meta = [
    userMessage.timestamp ? formatMessageTime(userMessage.timestamp) : '',
    userMessage.files?.length ? labels.files(userMessage.files.length) : '',
    userMessage.images?.length ? labels.images(userMessage.images.length) : '',
  ].filter(Boolean);

  return {
    id: `turn-${userIndex}-${assistantIndex ?? 'pending'}`,
    targetIndex: userIndex,
    relatedIndices: assistantIndex == null ? [userIndex] : [userIndex, assistantIndex],
    tone: 'user',
    title,
    snippet: assistantSnippet || userSnippet,
    meta,
  };
}

function buildMarkers(messages: Message[], labels: MinimapLabels): ChatMinimapMarker[] {
  const markers: ChatMinimapMarker[] = [];

  for (let index = 0; index < messages.length; index += 1) {
    const message = messages[index];

    if (message.role !== 'user') {
      markers.push(buildStandaloneMarker(message, index, labels));
      continue;
    }

    let nextUserIndex = messages.length;
    for (let scan = index + 1; scan < messages.length; scan += 1) {
      if (messages[scan].role === 'user') {
        nextUserIndex = scan;
        break;
      }
    }

    let finalAssistantIndex: number | null = null;
    for (let scan = nextUserIndex - 1; scan > index; scan -= 1) {
      if (messages[scan].role === 'assistant') {
        finalAssistantIndex = scan;
        break;
      }
    }

    markers.push(buildTurnMarker(
      message,
      index,
      finalAssistantIndex == null ? null : messages[finalAssistantIndex],
      finalAssistantIndex,
      labels,
    ));

    index = nextUserIndex - 1;
  }

  return markers;
}

export const ChatMinimap: React.FC<ChatMinimapProps> = ({
  messages,
  scrollContainerRef,
  onJumpToMessage,
}) => {
  const { t } = useI18n();
  const railRef = useRef<HTMLDivElement | null>(null);
  const [scrollCenterTop, setScrollCenterTop] = useState(50);
  const [hoveredMarkerId, setHoveredMarkerId] = useState<string | null>(null);
  const [hoverPercent, setHoverPercent] = useState<number | null>(null);

  const labels = useMemo<MinimapLabels>(() => ({
    user: t('chatWindow.minimapPreview.user'),
    assistant: t('chatWindow.minimapPreview.assistant'),
    notice: t('chatWindow.minimapPreview.notice'),
    activity: t('chatWindow.minimapPreview.activity'),
    files: (count) => t('chatWindow.minimapPreview.files', { count }),
    images: (count) => t('chatWindow.minimapPreview.images', { count }),
  }), [t]);

  const markers = useMemo(
    () => buildMarkers(messages, labels),
    [messages, labels],
  );

  // Ticks are spaced evenly by their order in the marker list, not by
  // message height — a uniform interval regardless of how long each turn
  // is. The rail is inset top/bottom so the first/last ticks aren't flush.
  const getMarkerTop = useCallback((marker: ChatMinimapMarker): number => {
    const order = markers.indexOf(marker);
    if (order < 0 || markers.length === 1) return 50;
    return RAIL_INSET_PERCENT + (order / (markers.length - 1)) * (100 - 2 * RAIL_INSET_PERCENT);
  }, [markers]);

  const getNearestMarkerAtPercent = useCallback((percent: number): ChatMinimapMarker | null => {
    if (markers.length === 0) return null;
    return markers.reduce((nearest, marker) => {
      const nearestDistance = Math.abs(getMarkerTop(nearest) - percent);
      const markerDistance = Math.abs(getMarkerTop(marker) - percent);
      return markerDistance < nearestDistance ? marker : nearest;
    }, markers[0]);
  }, [getMarkerTop, markers]);

  const hoveredMarker = hoveredMarkerId == null ? null : markers.find(marker => marker.id === hoveredMarkerId) ?? null;
  const hoveredTop = hoveredMarker ? getMarkerTop(hoveredMarker) : 50;
  const previewTop = Math.max(12, Math.min(88, hoveredTop));

  const updateMetrics = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el || el.scrollHeight <= el.clientHeight) {
      setScrollCenterTop(50);
      return;
    }

    setScrollCenterTop(Math.max(0, Math.min(100, ((el.scrollTop + el.clientHeight / 2) / el.scrollHeight) * 100)));
  }, [scrollContainerRef]);

  useEffect(() => {
    updateMetrics();
    const el = scrollContainerRef.current;
    if (!el) return;

    el.addEventListener('scroll', updateMetrics, { passive: true });
    const resizeObserver = new ResizeObserver(updateMetrics);
    resizeObserver.observe(el);
    if (el.firstElementChild) resizeObserver.observe(el.firstElementChild);

    return () => {
      el.removeEventListener('scroll', updateMetrics);
      resizeObserver.disconnect();
    };
  }, [markers.length, scrollContainerRef, updateMetrics]);

  const scrollFromRailPointer = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    const rail = railRef.current;
    const el = scrollContainerRef.current;
    if (!rail || !el || el.scrollHeight <= el.clientHeight) return;

    const rect = rail.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height));
    el.scrollTo({ top: ratio * (el.scrollHeight - el.clientHeight), behavior: 'smooth' });
  }, [scrollContainerRef]);

  const updateHoverFromPointer = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    const rail = railRef.current;
    if (!rail) return;

    const rect = rail.getBoundingClientRect();
    const percent = Math.max(0, Math.min(100, ((event.clientY - rect.top) / rect.height) * 100));
    setHoverPercent(percent);
    setHoveredMarkerId(getNearestMarkerAtPercent(percent)?.id ?? null);
  }, [getNearestMarkerAtPercent]);

  // Below this, the conversation fits on screen and a near-empty rail
  // just looks sparse — skip the minimap entirely until it earns its place.
  if (markers.length < MIN_MARKERS_TO_SHOW) {
    return null;
  }

  return (
    <div
      className="chat-minimap absolute right-3 top-1/2 z-20 hidden -translate-y-1/2 md:block pointer-events-none"
      aria-label={t('chatWindow.minimapLabel')}
      onMouseLeave={() => {
        setHoveredMarkerId(null);
        setHoverPercent(null);
      }}
    >
      {hoveredMarker && (
        <div
          className="chat-minimap-preview pointer-events-none"
          style={{
            top: `${previewTop}%`,
          }}
        >
          <div className="chat-minimap-preview-accent" />
          <div className="min-w-0">
            <div className="truncate text-[13px] font-semibold leading-snug text-neutral-900 dark:text-neutral-50">
              {hoveredMarker.title}
            </div>
            {hoveredMarker.snippet && (
              <div className="mt-1 line-clamp-2 text-[12px] leading-relaxed text-neutral-500 dark:text-neutral-300">
                {hoveredMarker.snippet}
              </div>
            )}
            {hoveredMarker.meta.length > 0 && (
              <div className="mt-2 flex min-w-0 items-center gap-2 text-[10px] font-bold uppercase text-neutral-400 dark:text-neutral-500">
                {hoveredMarker.meta.map(item => (
                  <span key={item} className="truncate">{item}</span>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      <div
        ref={railRef}
        className="chat-minimap-rail pointer-events-auto"
        onPointerDown={scrollFromRailPointer}
        onPointerMove={updateHoverFromPointer}
        onPointerEnter={updateHoverFromPointer}
        title={t('chatWindow.minimapLabel')}
      >
        {markers.map(marker => {
          const top = getMarkerTop(marker);
          const waveCenter = hoverPercent ?? scrollCenterTop;
          const distance = Math.abs(top - waveCenter);
          const influence = Math.max(0, 1 - distance / 12);
          const isHovered = hoveredMarker?.id === marker.id;
          const isNearScrollCenter = hoverPercent == null && distance < 3;
          return (
            <button
              key={marker.id}
              type="button"
              className={`chat-minimap-marker ${markerToneClass[marker.tone]}${isHovered ? ' chat-minimap-marker-hovered' : ''}${isNearScrollCenter ? ' chat-minimap-marker-current' : ''}`}
              style={{
                top: `${top}%`,
                ['--minimap-wave' as string]: influence.toFixed(3),
              }}
              onPointerDown={(event) => event.stopPropagation()}
              onMouseEnter={() => {
                setHoveredMarkerId(marker.id);
                setHoverPercent(top);
              }}
              onFocus={() => {
                setHoveredMarkerId(marker.id);
                setHoverPercent(top);
              }}
              onBlur={() => {
                setHoveredMarkerId(null);
                setHoverPercent(null);
              }}
              onClick={(event) => {
                event.stopPropagation();
                onJumpToMessage(marker.targetIndex);
              }}
              title={t('chatWindow.jumpToMessage', { count: marker.targetIndex + 1 })}
              aria-label={t('chatWindow.jumpToMessage', { count: marker.targetIndex + 1 })}
            />
          );
        })}
      </div>
    </div>
  );
};
