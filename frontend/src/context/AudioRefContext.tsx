import { createContext, useContext, type RefObject } from "react";

export const AudioRefContext = createContext<RefObject<HTMLAudioElement | null> | null>(null);

export function useAudioElement(): RefObject<HTMLAudioElement | null> | null {
  return useContext(AudioRefContext);
}
