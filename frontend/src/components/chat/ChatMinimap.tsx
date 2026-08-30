import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { Message } from '../../types/api';
import {
  buildOrderByMessageIndex,
  isAtScrollEnd,
  orderForMessageIndex,
} from './chatMinimapPosition';
import { formatMessageTime } from '../../lib/chatUtils';
import { useI18n } from '../../i18n';
import { InformationPopover } from '../InformationPopover';

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
// Ticks always sit this far apart, whatever the conversation's length. A long
// chat used to squeeze every tick into MAX_RAIL_PX until they merged into one
// solid smear that could be neither read nor aimed at; past that height the
// track slides under the rail instead of compressing, so a tick stays a tick.
const TICK_INTERVAL_PX = 11;
const MAX_RAIL_PX = 272;
// Breathing room at both ends of the track: ticks are drawn centered on their
// offset, so the first and last would otherwise be clipped by the viewport.
const TRACK_PADDING_PX = 4;
// How far the hover wave reaches, in track pixels.
const HOVER_WAVE_PX = 30;

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

function buildStandaloneMarker(
  message: Message,
  index: number,
  labels: MinimapLabels
): ChatMinimapMarker {
  const tone = getMessageTone(message);
  const fallbackTitle =
    tone === 'user'
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
  labels: MinimapLabels
): ChatMinimapMarker {
  const title = previewTitle(userMessage.content || '', labels.user);
  const assistantSnippet = assistantMessage
    ? previewSnippet(assistantMessage.content || '', '')
    : '';
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

    markers.push(
      buildTurnMarker(
        message,
        index,
        finalAssistantIndex == null ? null : messages[finalAssistantIndex],
        finalAssistantIndex,
        labels
      )
    );

    index = nextUserIndex - 1;
  }

  return markers;
}

const ChatMinimapComponent: React.FC<ChatMinimapProps> = ({
  messages,
  scrollContainerRef,
  onJumpToMessage,
}) => {
  const { t } = useI18n();
  const trackRef = useRef<HTMLDivElement | null>(null);
  const [scrollCenterRatio, setScrollCenterRatio] = useState(0.5);
  const [railOffsetPx, setRailOffsetPx] = useState(0);
  const [hoveredMarkerId, setHoveredMarkerId] = useState<string | null>(null);
  const [hoverPx, setHoverPx] = useState<number | null>(null);

  const labels = useMemo<MinimapLabels>(
    () => ({
      user: t('chatWindow.minimapPreview.user'),
      assistant: t('chatWindow.minimapPreview.assistant'),
      notice: t('chatWindow.minimapPreview.notice'),
      activity: t('chatWindow.minimapPreview.activity'),
      files: (count) => t('chatWindow.minimapPreview.files', { count }),
      images: (count) => t('chatWindow.minimapPreview.images', { count }),
    }),
    [t]
  );

  const markers = useMemo(() => buildMarkers(messages, labels), [messages, labels]);

  // The track holds every tick at full spacing; the viewport shows as much of
  // it as fits and scrolls for the rest.
  const trackHeightPx =
    markers.length < 2 ? 0 : (markers.length - 1) * TICK_INTERVAL_PX + TRACK_PADDING_PX * 2;
  const viewportHeightPx = Math.min(MAX_RAIL_PX, trackHeightPx);
  const isScrollable = trackHeightPx > viewportHeightPx;

  const getMarkerTopPx = useCallback(
    (marker: ChatMinimapMarker): number => {
      const order = markers.indexOf(marker);
      if (order < 0) return TRACK_PADDING_PX;
      return TRACK_PADDING_PX + order * TICK_INTERVAL_PX;
    },
    [markers]
  );

  const getNearestMarkerAtPx = useCallback(
    (px: number): ChatMinimapMarker | null => {
      if (markers.length === 0) return null;
      return markers.reduce((nearest, marker) => {
        const nearestDistance = Math.abs(getMarkerTopPx(nearest) - px);
        const markerDistance = Math.abs(getMarkerTopPx(marker) - px);
        return markerDistance < nearestDistance ? marker : nearest;
      }, markers[0]);
    },
    [getMarkerTopPx, markers]
  );

  const hoveredMarker =
    hoveredMarkerId == null
      ? null
      : (markers.find((marker) => marker.id === hoveredMarkerId) ?? null);
  // The preview sits outside the clipped viewport, so it is placed in viewport
  // coordinates: the tick's offset in the track less how far the track has
  // been slid up.
  const previewTop = hoveredMarker
    ? getMarkerTopPx(hoveredMarker) - railOffsetPx
    : viewportHeightPx / 2;
  const scrollCenterPx =
    TRACK_PADDING_PX + scrollCenterRatio * Math.max(0, trackHeightPx - TRACK_PADDING_PX * 2);

  const orderByMessageIndex = useMemo(() => buildOrderByMessageIndex(markers), [markers]);

  const updateMetrics = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el || markers.length < 2 || el.scrollHeight <= el.clientHeight) {
      setScrollCenterRatio(0.5);
      return;
    }

    // Sitting at the end means the last turn is what is being read, even
    // though a short final message never reaches the middle of the viewport.
    if (isAtScrollEnd(el.scrollTop, el.clientHeight, el.scrollHeight)) {
      setScrollCenterRatio(1);
      return;
    }

    // Read the position off the DOM rather than off scrollTop.
    //
    // The ticks are laid out one per marker at a fixed spacing -- an ordinal
    // axis -- while scrollTop measures pixels. Those agree only if every
    // message is the same height, and they are not: a turn can be one line or
    // a thousand. Worse, the rail draws a tick for every message in the chat
    // while the scroller only holds the ones currently loaded, so a pixel
    // ratio over 30 mounted messages was being read against a track covering
    // 76 -- at the top of the scroller the marker sat near the first tick
    // while the reader was three quarters of the way through the history.
    //
    // Asking which message is actually at the middle of the viewport settles
    // both: it is the same axis the ticks use, and a message that is not
    // mounted cannot be the answer.
    const centerY = el.getBoundingClientRect().top + el.clientHeight / 2;
    const rows = el.querySelectorAll<HTMLElement>('[data-message-index]');

    let position: number | null = null;
    for (const row of Array.from(rows)) {
      const rect = row.getBoundingClientRect();
      if (rect.bottom < centerY) continue;
      const order = orderForMessageIndex(orderByMessageIndex, Number(row.dataset.messageIndex));
      if (order === null) break;
      // Advance smoothly through a tall turn instead of sticking to its tick
      // until the next one begins.
      const within =
        rect.height > 0 ? Math.min(1, Math.max(0, (centerY - rect.top) / rect.height)) : 0;
      position = order + within;
      break;
    }

    if (position === null) {
      // Past the last mounted row -- the reader is at the end.
      position = markers.length - 1;
    }

    setScrollCenterRatio(Math.max(0, Math.min(1, position / (markers.length - 1))));
  }, [scrollContainerRef, markers.length, orderByMessageIndex]);

  useEffect(() => {
    updateMetrics();
    const el = scrollContainerRef.current;
    if (!el) return;

    // Scroll fires far faster than the screen refreshes, and each event here
    // would otherwise re-render the whole rail. Coalesce to one update per
    // frame so dragging the scrollbar stays smooth while a turn streams.
    let frame: number | null = null;
    const scheduleUpdate = () => {
      if (frame !== null) return;
      frame = requestAnimationFrame(() => {
        frame = null;
        updateMetrics();
      });
    };

    el.addEventListener('scroll', scheduleUpdate, { passive: true });
    const resizeObserver = new ResizeObserver(scheduleUpdate);
    resizeObserver.observe(el);
    if (el.firstElementChild) resizeObserver.observe(el.firstElementChild);

    return () => {
      if (frame !== null) cancelAnimationFrame(frame);
      el.removeEventListener('scroll', scheduleUpdate);
      resizeObserver.disconnect();
    };
  }, [markers.length, scrollContainerRef, updateMetrics]);

  // Keep the stretch of conversation being read inside the rail's window. The
  // track is *slid* rather than scrolled: no scrollbar to put next to a rail
  // this thin, and the move is a transition, so a long chat's ticks glide into
  // place with the same motion the rail has when it fits on screen.
  // Suspended while the pointer is over the rail: pulling ticks out from under
  // the cursor mid-aim would make the rail impossible to use.
  useEffect(() => {
    if (!isScrollable) {
      setRailOffsetPx(0);
      return;
    }
    if (hoverPx !== null) return;
    const target = Math.max(
      0,
      Math.min(trackHeightPx - viewportHeightPx, scrollCenterPx - viewportHeightPx / 2)
    );
    setRailOffsetPx((previous) => (Math.abs(previous - target) < 1 ? previous : target));
  }, [hoverPx, isScrollable, scrollCenterPx, trackHeightPx, viewportHeightPx]);

  const scrollFromRailPointer = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      const track = trackRef.current;
      const el = scrollContainerRef.current;
      if (!track || !el || el.scrollHeight <= el.clientHeight) return;

      // Measured against the track rather than the viewport, so a click means
      // the same place in the conversation however the rail is scrolled.
      const rect = track.getBoundingClientRect();
      const ratio = Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height));
      el.scrollTo({ top: ratio * (el.scrollHeight - el.clientHeight), behavior: 'smooth' });
    },
    [scrollContainerRef]
  );

  const updateHoverFromPointer = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      const track = trackRef.current;
      if (!track) return;

      const rect = track.getBoundingClientRect();
      const px = Math.max(0, Math.min(rect.height, event.clientY - rect.top));
      setHoverPx(px);
      setHoveredMarkerId(getNearestMarkerAtPx(px)?.id ?? null);
    },
    [getNearestMarkerAtPx]
  );

  const clearHover = useCallback(() => {
    setHoveredMarkerId(null);
    setHoverPx(null);
  }, []);

  // Below this, the conversation fits on screen and a near-empty rail
  // just looks sparse — skip the minimap entirely until it earns its place.
  if (markers.length < MIN_MARKERS_TO_SHOW) {
    return null;
  }

  return (
    <div
      className="chat-minimap absolute right-3 top-1/2 z-20 hidden -translate-y-1/2 md:block pointer-events-none"
      aria-label={t('chatWindow.minimapLabel')}
      onMouseLeave={clearHover}
    >
      <div className="chat-minimap-rail" style={{ height: `${viewportHeightPx}px` }}>
        {hoveredMarker && (
          <InformationPopover
            className="chat-minimap-preview pointer-events-none"
            style={{
              top: `${previewTop}px`,
            }}
          >
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
                  {hoveredMarker.meta.map((item) => (
                    <span key={item} className="truncate">
                      {item}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </InformationPopover>
        )}

        <div
          className={`chat-minimap-viewport pointer-events-auto${
            isScrollable ? ' chat-minimap-viewport-clipped' : ''
          }`}
          onPointerDown={scrollFromRailPointer}
          onPointerMove={updateHoverFromPointer}
          onPointerEnter={updateHoverFromPointer}
          title={t('chatWindow.minimapLabel')}
        >
          <div
            ref={trackRef}
            className="chat-minimap-track"
            style={{
              height: `${trackHeightPx}px`,
              transform: `translateY(${-railOffsetPx}px)`,
            }}
          >
            {markers.map((marker) => {
              const top = getMarkerTopPx(marker);
              const hoverDistance = hoverPx == null ? null : Math.abs(top - hoverPx);
              const influence =
                hoverDistance == null ? 0 : Math.max(0, 1 - hoverDistance / HOVER_WAVE_PX);
              const isHovered = hoveredMarker?.id === marker.id;
              const isNearScrollCenter =
                hoverPx == null && Math.abs(top - scrollCenterPx) < TICK_INTERVAL_PX / 2;
              return (
                <button
                  key={marker.id}
                  type="button"
                  className={`chat-minimap-marker ${markerToneClass[marker.tone]}${isHovered ? ' chat-minimap-marker-hovered' : ''}${isNearScrollCenter ? ' chat-minimap-marker-current' : ''}`}
                  style={{
                    top: `${top}px`,
                    ['--minimap-wave' as string]: influence.toFixed(3),
                  }}
                  onPointerDown={(event) => event.stopPropagation()}
                  onMouseEnter={() => {
                    setHoveredMarkerId(marker.id);
                    setHoverPx(top);
                  }}
                  onFocus={() => {
                    setHoveredMarkerId(marker.id);
                    setHoverPx(top);
                  }}
                  onBlur={clearHover}
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
      </div>
    </div>
  );
};

// The rail re-renders on every scroll frame from its own state; without this it
// would also re-render on each of the parent's streaming-chunk renders and
// rebuild every marker preview from scratch.
export const ChatMinimap = React.memo(ChatMinimapComponent);
