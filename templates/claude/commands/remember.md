---
description: Store one deliberate, validated memory in Brain-Eleven for the current project
---

Use the Brain-Eleven validator to store the deliberate memory described by the
user. Treat the current working directory as the project root and pass its
opaque project identity; never persist the absolute path or a transcript.

Run:

```text
python "{{VAULT_PATH}}/scripts/remember.py" --vault "{{VAULT_PATH}}" --project-root "$PWD" --type <decision|lesson|observation|open_loop> --content "$ARGUMENTS"
```

Capture only an explicit decision, lesson, observation, or open loop. Do not
capture secrets, credentials, tokens, or the full conversation.
