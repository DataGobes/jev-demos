import { Suspense } from "react";
import { Cringometer } from "@/components/Cringometer";
import { RecordingCaptions } from "@/components/RecordingCaptions";

export default function Home() {
  return (
    <>
      <Cringometer />
      <Suspense fallback={null}>
        <RecordingCaptions />
      </Suspense>
    </>
  );
}
