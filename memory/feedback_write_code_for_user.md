---
name: feedback_write_code_for_user
description: User prefers to write code themselves — provide the data/logic flow as text, not edits
metadata:
  type: feedback
---

User wants to write code manually as part of understanding the rewrite. When asked for implementation, give the dataflow or logic steps as text so they can type it themselves — do not apply edits to the file.

**Why:** The rewrite is intentional and manual — the goal is comprehension, not speed.

**How to apply:** When the user asks "how do I do X" or "what should this look like", describe the flow in plain text. Only edit files when the user explicitly asks to fix a bug or error.
