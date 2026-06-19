"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Modal } from "@/components/modal";
import { Badge, Button, Card, Icons, Spinner, Textarea } from "@/components/ui";
import { Markdown } from "@/components/markdown";
import { useToast } from "@/components/toast";
import {
  fetchAdaptiveSummary,
  fetchQuiz,
  submitAssessment,
  type Answer,
  type AssessResponse,
  type QuizQuestion,
} from "@/lib/comprehension";

type Step = "loading" | "questions" | "submitting" | "results" | "error";

const orderQuestions = (qs: QuizQuestion[]) =>
  [...qs].sort((a, b) => (a.type === b.type ? 0 : a.type === "comprehension" ? -1 : 1));

export function ComprehensionQuiz({
  open,
  onClose,
  transcript,
}: {
  open: boolean;
  onClose: () => void;
  transcript: string;
}) {
  const router = useRouter();
  const { error: toastError } = useToast();

  const [step, setStep] = useState<Step>("loading");
  const [questions, setQuestions] = useState<QuizQuestion[]>([]);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [result, setResult] = useState<AssessResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [validation, setValidation] = useState(false);
  // Adapted-summary sub-state (auto-runs after submit, lives inside the results view).
  const [adapting, setAdapting] = useState(false);
  const [adapted, setAdapted] = useState<string | null>(null);
  const [adaptError, setAdaptError] = useState<string | null>(null);

  const handleError = useCallback(
    (e: unknown) => {
      const msg = e instanceof Error ? e.message : String(e);
      if (msg === "UNAUTHORIZED") {
        router.push("/login");
        return;
      }
      setErrorMsg(msg);
      setStep("error");
    },
    [router],
  );

  const loadQuiz = useCallback(async () => {
    setResult(null);
    setAdapted(null);
    setAdaptError(null);
    setValidation(false);
    setErrorMsg(null);
    setStep("loading");
    try {
      const data = await fetchQuiz(transcript);
      const qs = orderQuestions(data.questions ?? []);
      setQuestions(qs);
      setAnswers(Object.fromEntries(qs.map((q) => [q.id, ""])));
      setStep("questions");
    } catch (e) {
      handleError(e);
    }
  }, [transcript, handleError]);

  useEffect(() => {
    if (open) loadQuiz();
  }, [open, loadQuiz]);

  // Regenerate the summary adapted to the user's level (auto after submit, or manual retry).
  const runRegenerate = useCallback(async () => {
    setAdaptError(null);
    setAdapting(true);
    try {
      const res = await fetchAdaptiveSummary(transcript);
      setAdapted(res.summary);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      if (msg === "UNAUTHORIZED") {
        router.push("/login");
        return;
      }
      setAdaptError(msg);
      toastError("Couldn't adapt the summary", msg);
    } finally {
      setAdapting(false);
    }
  }, [transcript, router, toastError]);

  async function submit() {
    if (!questions.every((q) => (answers[q.id] ?? "").trim())) {
      setValidation(true);
      return;
    }
    setStep("submitting");
    try {
      const payload: Answer[] = questions.map((q) => ({
        question: q.question,
        type: q.type,
        answer: (answers[q.id] ?? "").trim(),
      }));
      setResult(await submitAssessment(transcript, payload));
      setStep("results");
    } catch (e) {
      handleError(e);
    }
  }

  const comprehension = questions.filter((q) => q.type === "comprehension");
  const feedback = questions.filter((q) => q.type === "feedback");
  const levelTone = (lvl: string) => (lvl === "high" ? "success" : lvl === "low" ? "warn" : "accent");

  const body = (() => {
    if (step === "loading") return <Center label="Generating your quiz…" />;
    if (step === "submitting") return <Center label="Checking your answers…" />;
    if (step === "error")
      return (
        <Card className="p-4">
          <div className="flex items-start gap-2 text-sm text-fg">
            <Icons.alert className="mt-0.5 h-4 w-4 shrink-0 text-warn" />
            <span>{errorMsg}</span>
          </div>
        </Card>
      );
    if (step === "questions")
      return (
        <div className="space-y-4">
          {comprehension.map((q, i) => (
            <QField
              key={q.id}
              label={`Question ${i + 1}`}
              question={q.question}
              name={`q-${q.id}`}
              options={q.options}
              value={answers[q.id] ?? ""}
              invalid={validation && !(answers[q.id] ?? "").trim()}
              onChange={(v) => setAnswers((a) => ({ ...a, [q.id]: v }))}
            />
          ))}
          {feedback.length > 0 && (
            <div className="space-y-4 border-t border-border pt-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted">Your opinion</p>
              {feedback.map((q) => (
                <QField
                  key={q.id}
                  label="Feedback"
                  question={q.question}
                  name={`q-${q.id}`}
                  value={answers[q.id] ?? ""}
                  invalid={validation && !(answers[q.id] ?? "").trim()}
                  onChange={(v) => setAnswers((a) => ({ ...a, [q.id]: v }))}
                />
              ))}
            </div>
          )}
        </div>
      );
    if (step === "results" && result)
      return (
        <div className="space-y-4">
          <div className="flex items-center gap-3">
            <span className="text-2xl font-semibold text-fg">{Math.round(result.score_pct)}%</span>
            <Badge tone={levelTone(result.understanding_level)}>{result.understanding_level}</Badge>
          </div>
          <div className="space-y-2">
            {(result.per_question ?? []).map((p) => {
              const q = comprehension.find((c) => c.id === p.id);
              return (
                <div key={p.id} className="flex items-start gap-2 text-sm">
                  {p.correct ? (
                    <Icons.checkCircle className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                  ) : (
                    <Icons.alert className="mt-0.5 h-4 w-4 shrink-0 text-warn" />
                  )}
                  <div>
                    {q && <p className="text-fg">{q.question}</p>}
                    {p.explanation && <p className="text-muted">{p.explanation}</p>}
                  </div>
                </div>
              );
            })}
          </div>
          {result.notes && (
            <Card className="p-3 text-sm text-muted">
              <Markdown>{result.notes}</Markdown>
            </Card>
          )}

          {/* Adapted summary — generated ON DEMAND (one click) from the answers + opinion */}
          <div className="border-t border-border pt-4">
            <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-accent-text">
              <Icons.sparkles className="h-3.5 w-3.5" /> Your summary, adapted to you
            </p>
            {adapting ? (
              <div className="flex items-center gap-2 text-sm text-muted">
                <Spinner className="h-4 w-4" /> Tailoring it to your level…
              </div>
            ) : adapted ? (
              <>
                <Card className="p-3 text-sm">
                  <Markdown>{adapted}</Markdown>
                </Card>
                <Button variant="ghost" size="sm" className="mt-2" onClick={runRegenerate}>
                  <Icons.refresh className="h-4 w-4" /> Regenerate
                </Button>
              </>
            ) : adaptError ? (
              <div className="text-sm">
                <p className="mb-2 flex items-start gap-2 text-muted">
                  <Icons.alert className="mt-0.5 h-4 w-4 shrink-0 text-warn" />
                  {adaptError}
                </p>
                <Button variant="outline" size="sm" onClick={runRegenerate}>
                  <Icons.refresh className="h-4 w-4" /> Try again
                </Button>
              </div>
            ) : (
              <Button variant="primary" size="sm" onClick={runRegenerate}>
                <Icons.sparkles className="h-4 w-4" /> Adapt this summary to my level
              </Button>
            )}
          </div>
        </div>
      );
    return null;
  })();

  const footer = (() => {
    if (step === "questions")
      return (
        <>
          <Button variant="ghost" onClick={onClose}>
            Close
          </Button>
          <Button variant="primary" onClick={submit}>
            Submit answers
          </Button>
        </>
      );
    if (step === "results")
      return (
        <Button variant="ghost" onClick={onClose}>
          Done
        </Button>
      );
    if (step === "error")
      return (
        <>
          <Button variant="ghost" onClick={onClose}>
            Close
          </Button>
          <Button variant="primary" onClick={loadQuiz}>
            Try again
          </Button>
        </>
      );
    return (
      <Button variant="ghost" onClick={onClose}>
        Close
      </Button>
    );
  })();

  return (
    <Modal open={open} onClose={onClose} title="Test my understanding" footer={footer}>
      <div className="max-h-[65vh] overflow-y-auto pr-1 -mr-1">{body}</div>
    </Modal>
  );
}

function Center({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-10 text-sm text-muted">
      <Spinner className="h-6 w-6" />
      <span>{label}</span>
    </div>
  );
}

function QField({
  label,
  question,
  value,
  invalid,
  onChange,
  options,
  name,
}: {
  label: string;
  question: string;
  value: string;
  invalid: boolean;
  onChange: (v: string) => void;
  options?: string[];
  name?: string;
}) {
  const isMcq = Array.isArray(options) && options.length > 0;
  return (
    <div>
      <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted">{label}</p>
      <p className="mb-2 text-sm text-fg">{question}</p>
      {isMcq ? (
        <div className="space-y-1.5">
          {options!.map((opt, i) => {
            const selected = value === opt;
            return (
              <label
                key={i}
                className={`flex cursor-pointer items-start gap-2 rounded-lg border px-3 py-2 text-sm transition-colors ${
                  selected
                    ? "border-accent bg-accent-soft text-accent-text"
                    : "border-border hover:border-border-strong"
                }`}
              >
                <input
                  type="radio"
                  name={name}
                  checked={selected}
                  onChange={() => onChange(opt)}
                  className="mt-0.5 accent-accent"
                />
                <span>{opt}</span>
              </label>
            );
          })}
        </div>
      ) : (
        <Textarea
          rows={2}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className={invalid ? "border-danger" : ""}
          placeholder="Your answer…"
        />
      )}
      {invalid && <p className="mt-1 text-xs text-danger">Please answer this question.</p>}
    </div>
  );
}
