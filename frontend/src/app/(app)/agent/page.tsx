"use client";

import { LearningAgent } from "@/components/learning-agent";

export default function AgentPage() {
  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-6 sm:px-5 sm:py-8">
      <div className="mb-5">
        <h1 className="text-lg font-semibold">Your learning agent</h1>
        <p className="text-sm text-muted">
          A stateful Hermes agent: it summarizes videos, learns your preferences, and writes its own
          memory + skills as you talk to it. Watch the “What it learned” panel grow.
        </p>
      </div>
      <LearningAgent />
    </div>
  );
}
