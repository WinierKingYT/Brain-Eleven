---
description: Capture one explicit memory in the Brain-Eleven vault from any project.
---

# Remember Command

Use this command only for an explicitly requested memory capture. It works from
any project and does not require that project to be on the proactive opt-in list.

Run the Brain-Eleven capture adapter with the current working directory as the
project context:

```bash
python "{{VAULT_PATH}}/scripts/remember.py" --vault "{{VAULT_PATH}}" --project-root . --type decision --content "$ARGUMENTS"
```

If the memory is not a decision, replace `--type decision` with `lesson`,
`open_loop`, or `observation`. Add `--project <short-project-id>` when the
directory name is not an appropriate provenance label.

The command reuses Brain-Eleven's validator, fingerprint deduplication,
quality scoring, atomic persistence and graph rebuild. Never pass secrets,
credentials, tokens, private keys or full session transcripts as content.
