"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { Badge, Button, Card, Icons, Spinner, Textarea } from "@/components/ui";
import { Markdown } from "@/components/markdown";
import { fetchAgentState, sendAgentMessage, type AgentStateResponse } from "@/lib/comprehension";

type Msg = { role: "user" | "agent"; content: string };

const STARTERS = [
  "Hi — be my video-learning assistant. I'm a beginner; explain like I'm new.",
  "I prefer story-style summaries, beginner level, and always decode jargon.",
  "For technical videos always summarize as: why it matters → 3 key points → jargon decoded. Save that as your standard procedure.",
];

export function LearningAgent() {
  const router = useRouter();
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [state, setState] = useState<AgentStateResponse | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  function onAuthError(e: unknown): boolean {
    if (e instanceof Error && e.message === "UNAUTHORIZED") {
      router.push("/login");
      return true;
    }
    return false;
  }

  async function refreshState() {
    try {
      setState(await fetchAgentState());
    } catch (e) {
      onAuthError(e); // non-fatal otherwise
    }
  }

  useEffect(() => {
    void refreshState();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  async function send(text: string) {
    const msg = text.trim();
    if (!msg || sending) return;
    setError(null);
    setInput("");
    setMessages((m) => [...m, { role: "user", content: msg }]);
    setSending(true);
    try {
      const { reply } = await sendAgentMessage(msg);
      setMessages((m) => [...m, { role: "agent", content: reply }]);
      // The self-improvement review runs in the BACKGROUND after the reply — give it a
      // few seconds, then refresh the "what it learned" panel so new memory/skills show.
      setTimeout(() => void refreshState(), 3500);
    } catch (e) {
      if (onAuthError(e)) return;
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_320px]">
      {/* Chat */}
      <Card className="flex h-[70vh] flex-col p-0">
        <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto p-5">
          {messages.length === 0 && (
            <div className="text-sm text-muted">
              <p className="mb-3">
                Talk to your Hermes learning agent — tell it your preferences and teach it how you
                like summaries. It remembers you and writes its own skills as you go. Try:
              </p>
              <div className="flex flex-col gap-2">
                {STARTERS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => send(s)}
                    disabled={sending}
                    className="rounded-lg border border-border px-3 py-2 text-left transition-colors hover:border-accent hover:text-fg disabled:opacity-50"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
              <div
                className={
                  m.role === "user"
                    ? "max-w-[85%] rounded-2xl bg-accent px-4 py-2 text-sm text-white"
                    : "max-w-[85%] rounded-2xl border border-border px-4 py-2 text-sm"
                }
              >
                {m.role === "agent" ? <Markdown>{m.content}</Markdown> : m.content}
              </div>
            </div>
          ))}
          {sending && (
            <div className="flex items-center gap-2 text-sm text-muted">
              <Spinner className="h-4 w-4" /> Thinking…
            </div>
          )}
        </div>
        {error && (
          <div className="flex items-start gap-2 border-t border-border px-5 py-2 text-sm text-warn">
            <Icons.alert className="mt-0.5 h-4 w-4 shrink-0" /> {error}
          </div>
        )}
        <form
          className="flex gap-2 border-t border-border p-3"
          onSubmit={(e) => {
            e.preventDefault();
            void send(input);
          }}
        >
          <Textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send(input);
              }
            }}
            disabled={sending}
            rows={2}
            placeholder="Message your agent… (Enter to send, Shift+Enter for a newline)"
            className="flex-1 resize-none"
          />
          <Button type="submit" disabled={sending || !input.trim()}>
            <Icons.sparkles className="h-4 w-4" /> Send
          </Button>
        </form>
      </Card>

      {/* What your agent has learned (live self-improvement) */}
      <Card className="flex max-h-[70vh] flex-col overflow-hidden p-5">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-widest text-accent-text">
            <Icons.sparkles className="h-3.5 w-3.5" /> What it learned
          </h2>
          <button
            type="button"
            onClick={() => void refreshState()}
            title="Refresh"
            className="text-muted transition-colors hover:text-fg"
          >
            <Icons.refresh className="h-4 w-4" />
          </button>
        </div>
        <div className="flex-1 space-y-4 overflow-y-auto text-sm">
          <section>
            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">About you (USER.md)</p>
            {state?.user_profile?.trim() ? (
              <Markdown>{state.user_profile}</Markdown>
            ) : (
              <p className="text-muted">Nothing yet — tell it your preferences.</p>
            )}
          </section>
          <section>
            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Memory (MEMORY.md)</p>
            {state?.memory?.trim() ? (
              <Markdown>{state.memory}</Markdown>
            ) : (
              <p className="text-muted">Nothing yet.</p>
            )}
          </section>
          <section>
            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Skills it wrote</p>
            {state?.new_skills?.length ? (
              <div className="flex flex-wrap gap-1.5">
                {state.new_skills.map((n) => (
                  <Badge key={n}>✨ {n}</Badge>
                ))}
              </div>
            ) : (
              <p className="text-muted">No new skill yet — teach it a procedure.</p>
            )}
            {state?.skills?.length ? (
              <p className="mt-1.5 text-xs text-muted">{state.skills.length} skills available total</p>
            ) : null}
          </section>
        </div>
      </Card>
    </div>
  );
}
