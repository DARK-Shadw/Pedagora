"use client";

import { useCallback, useRef } from "react";

interface SpeechQueueItem {
  text: string;
  speechType: string;
}

/**
 * Manages speech queue — processes TTS items sequentially.
 * Calls onSpeechDone when each item finishes (to notify backend).
 * Calls onSpeechStart when TTS begins playing.
 */
export function useSpeechQueue(
  speakFn: (text: string, onEnd: () => void, onStart?: () => void) => void,
  onSpeechDone: () => void,
  onSpeechStart?: (text: string, speechType: string) => void,
) {
  const queueRef = useRef<SpeechQueueItem[]>([]);
  const isProcessingRef = useRef(false);

  const processQueue = useCallback(() => {
    if (isProcessingRef.current || queueRef.current.length === 0) return;
    isProcessingRef.current = true;

    const item = queueRef.current.shift()!;
    speakFn(
      item.text,
      () => {
        // onEnd — speech finished
        isProcessingRef.current = false;
        onSpeechDone();
        // Process next item
        processQueue();
      },
      () => {
        // onStart — speech began playing
        onSpeechStart?.(item.text, item.speechType);
      },
    );
  }, [speakFn, onSpeechDone, onSpeechStart]);

  const enqueue = useCallback((text: string, speechType: string = "teaching") => {
    queueRef.current.push({ text, speechType });
    processQueue();
  }, [processQueue]);

  const clear = useCallback(() => {
    queueRef.current = [];
    isProcessingRef.current = false;
  }, []);

  return { enqueue, clear };
}
