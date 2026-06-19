# Hermes skills for the comprehension features

Three skills that encode the adaptive comprehension workflow. The agent loads them
when the matching endpoint runs (the `agent_client.py` prompts reference them by
name), and the **assess** skill adapts each user's profile from their answers.

```
adaptive-video-summary   →  summary tailored to the user's profile
comprehension-quiz       →  N topic questions + 2 feedback questions
assess-comprehension     →  grade answers, UPDATE the profile  ⟲ feeds the summary
```

## Install into the Hermes sidecar

Copy each skill folder into the Hermes profile's skills directory:

- Linux/macOS/WSL: `~/.hermes/skills/`
- Windows native:  `%LOCALAPPDATA%\hermes\skills\`

```bash
# from this folder, once Hermes is set up:
cp -r adaptive-video-summary comprehension-quiz assess-comprehension ~/.hermes/skills/
# Windows (PowerShell):
#   Copy-Item -Recurse adaptive-video-summary,comprehension-quiz,assess-comprehension $env:LOCALAPPDATA\hermes\skills\
```

Then enable the **skills** toolset on the sidecar (alongside **web**) so the agent
can load them:

```bash
hermes tools     # enable: web, skills   |   disable: terminal, code, browser, delegate
```

Verify they're registered:
```bash
hermes skills              # should list the three skills
```

## Notes
- The skills are the **single source of truth** for the procedure. To change how
  summaries adapt, edit the SKILL.md — no app code change needed.
- If the skills aren't installed (or the skills toolset is off), the endpoints still
  work: `agent_client.py` carries an inline fallback of the same procedure.
- Hermes can self-improve these skills over time (its background review / curator)
  if you run it interactively.
