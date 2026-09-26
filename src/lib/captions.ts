/**
 * Caption script for recording mode (see src/components/RecordingCaptions.tsx).
 *
 * Only active when the page URL has `?record=1`. Keys 1-6 (via Alt/Option+digit)
 * show the matching caption below; 0/Escape hides it. Kept as a flat array so
 * the on-screen order matches the key order 1:1.
 */

export interface Caption {
  key: string;
  text: string;
}

export const CAPTIONS: readonly Caption[] = [
  { key: "1", text: "I built an AI that judges LinkedIn posts" },
  { key: "2", text: "It scores while you type" },
  { key: "3", text: "8 questions · 1 API call · ~250 ms" },
  {
    key: "4",
    text: "Re-weighting = zero API calls. The judgments are data, the scoring is just code.",
  },
  { key: "5", text: "So I ran this post through it." },
  { key: "6", text: "I have never been prouder." },
];
