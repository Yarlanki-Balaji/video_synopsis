// Client for the per-user comprehension endpoints (Hermes-backed).
// Mirrors the workbench pattern: api() + errorDetail(), 401 -> "UNAUTHORIZED".
import { api, errorDetail } from "@/lib/api";

export type QuizQuestion = {
  id: number;
  type: "comprehension" | "feedback";
  question: string;
  options?: string[]; // present for MCQ comprehension questions
};
export type QuizResponse = { questions: QuizQuestion[] };
export type Answer = { question: string; type: "comprehension" | "feedback"; answer: string };
export type PerQuestion = { id: number; correct: boolean; explanation: string };
export type AssessResponse = {
  score_pct: number;
  understanding_level: string;
  per_question: PerQuestion[];
  updated_profile: { reading_level: string; style_notes: string[]; understanding_history: number[] };
  notes: string;
};
export type AdaptiveSummaryResponse = { summary: string; profile_used: unknown };

async function post<T>(path: string, body: unknown, fallback: string): Promise<T> {
  const res = await api(path, { method: "POST", body: JSON.stringify(body) });
  if (res.status === 401) throw new Error("UNAUTHORIZED");
  if (!res.ok) throw new Error(await errorDetail(res, fallback));
  return (await res.json()) as T;
}

export function fetchQuiz(transcript: string, numQuestions = 5) {
  return post<QuizResponse>(
    "/api/comprehension/quiz",
    { transcript, num_questions: numQuestions },
    "Could not generate the quiz",
  );
}

export function submitAssessment(transcript: string, answers: Answer[]) {
  return post<AssessResponse>(
    "/api/comprehension/assess",
    { transcript, answers },
    "Could not grade your answers",
  );
}

export function fetchAdaptiveSummary(transcript: string, summaryType = "detailed") {
  return post<AdaptiveSummaryResponse>(
    "/api/comprehension/summary",
    { transcript, summary_type: summaryType },
    "Could not generate the summary",
  );
}

/** Build the content to quiz on from a job's summaries (most-informative first).
 *  Summaries are short, so this stays well under the model's token budget. */
const SUMMARY_ORDER = ["detailed", "notes", "chapters", "bullets", "eli5", "brief", "mindmap"];
export function summaryContent(summaries?: Record<string, string>): string {
  if (!summaries) return "";
  const keys = Object.keys(summaries);
  const ordered = [
    ...SUMMARY_ORDER.filter((k) => summaries[k]),
    ...keys.filter((k) => !SUMMARY_ORDER.includes(k)),
  ];
  return ordered.map((k) => summaries[k]).filter(Boolean).join("\n\n");
}
