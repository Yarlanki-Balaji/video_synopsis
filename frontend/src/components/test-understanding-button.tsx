"use client";

import { useState } from "react";

import { Button, Icons } from "@/components/ui";
import { ComprehensionQuiz } from "@/components/comprehension-quiz";

export function TestUnderstandingButton({
  transcript,
  className,
}: {
  transcript?: string | null;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const hasTranscript = !!transcript && transcript.trim().length >= 50;
  return (
    <>
      <Button
        variant="outline"
        size="sm"
        className={className}
        disabled={!hasTranscript}
        title={hasTranscript ? undefined : "Transcript not available yet"}
        onClick={() => setOpen(true)}
      >
        <Icons.shield className="h-4 w-4" /> Test my understanding
      </Button>
      <ComprehensionQuiz open={open} onClose={() => setOpen(false)} transcript={(transcript ?? "").trim()} />
    </>
  );
}
