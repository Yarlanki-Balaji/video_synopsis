# Hermes Agent Architecture — explained through *your* video-learning agent

**The throughline:** Imagine you hired a brilliant personal **video tutor**. The first week they're generic. But every time you talk to them, they jot down how *you* like things, and when they figure out a good way to do something, they write themselves a playbook. A month later they summarize videos exactly the way you learn best — without you re-explaining. **That tutor is Hermes, and your "Learning agent" page is where you meet them.**

---

### Entry points — one tutor, many doors
You can reach the tutor three ways: walk into their office (**CLI**), phone them through your own software (**API**), or text them on WhatsApp/Slack/Telegram (**gateway**). Same brain behind every door.

**In your project:** your FastAPI backend phones the tutor through the **API** — the Hermes sidecar on `:8642`. (You don't use the messaging gateway; that's for chat-app bots.)

### The agent loop — how the tutor handles one message
Every message runs a perceive → think → act cycle:

1. **Build context** — before answering, the tutor pulls up what they know: who they are (`SOUL.md`), their notes on *you* (`USER.md`), loose facts (`MEMORY.md`), and the past conversation.
2. **Think (LLM)** — all that goes to the model, which decides whether to *use a tool* (web search, file ops) or just answer.
3. **Respond** — it writes the reply.
4. **Update memory — periodically, in the background.** This is the nuance most explanations get wrong: the tutor doesn't rewrite their notes after *every* sentence. Every so often (a "nudge," ~every several turns), a **background reviewer** re-reads the conversation and asks *"did I learn anything worth keeping?"* — then quietly files it.

**In your project:** each message to `/api/comprehension/agent` is one loop. After a couple of turns, that background reviewer wrote your real `USER.md`: *beginner · story-style · decode jargon · "technical videos = why-it-matters → 3 points → jargon decoded."*

### Skills / self-improvement — the tutor writes their own playbooks
This is Hermes' headline feature. When the tutor works out a repeatable method — or you explicitly teach them one — the background reviewer saves it as a **skill** (`SKILL.md`): a reusable procedure they'll reach for next time. Skills live with the tutor and apply to everyone they help (they're profile-wide, not per-person).

**In your project:** when you said *"always summarize technical videos as why-it-matters → 3 key points → jargon decoded — save that as your standard procedure,"* Hermes **wrote `technical-video-summary/SKILL.md` itself** — no code told it to. That's the self-improving loop, live.

### Memory — three layers
- **Markdown notes** always in hand: `SOUL.md` (personality/role), `USER.md` (evolving understanding of you), `MEMORY.md` (stray facts).
- **A filing cabinet (SQLite):** full transcripts of every session, kept for exact lookups.
- **An optional research assistant (Mem0 / SuperMemory / Honcho):** off by default; when enabled, it does *similarity search* — surfacing the most relevant past note from the very first message, and isolating memory **per user**.

**In your project:** you use the built-in notes + transcript DB. You skipped the external assistant (Honcho) on purpose — it's only needed when many distinct users must not share memory; for a single-user demo the built-in notes are the real thing.

### Context compression — summarizing the long meeting
The model can only hold so much at once. When the conversation grows past about **half** the model's limit, Hermes **compresses** the old history into a tight summary — preserving the goals, decisions, and constraints — so a long session never overflows.

**Real-life:** like an assistant who, after a 2-hour meeting, keeps a one-page recap instead of the full transcript in their head.

### Gateway & session manager — *(Hermes offers it; your app doesn't use it)*
The gateway listens across messaging platforms on an async loop, rebuilds each conversation from the SQLite transcripts, and a **session manager** decides what to do if you interrupt mid-task — pause, switch, or queue.

**In your project:** you use the API server (part of this), where a **stable session id** makes the server keep your conversation going turn-to-turn. *That stable session is exactly the fix that turned the integration from a dumb proxy into a real stateful agent.*

### Cron jobs — *(Hermes offers it; your app doesn't use it)*
A once-a-minute loop checks `jobs.json` for scheduled tasks ("every morning, brief me on AI news"), runs them, and messages the result to your home platform — no manual trigger.

**Real-life:** standing orders you give an assistant once and never repeat.

---

**Why it matters (the one-liner):** *The app talks to Hermes as a stateful agent. As someone uses it, Hermes learns their preferences into its own `USER.md` and writes its own reusable `SKILL.md` — with no code instructing it to. It gets better the more it's used.*
