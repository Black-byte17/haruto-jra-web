#!/usr/bin/env bash
# UserPromptSubmit フック：JRA予想・検証らしい依頼のときだけ、中枢マスターの適用をリマインドする。
input="$(cat)"
if printf '%s' "$input" | grep -qE 'HARUTO|ハルト|完全予想|予想|買い目|馬券|検証|◎|note版|競馬|[0-9]+R'; then
  cat <<'MSG'
[HARUTO JRA 中枢] JRAレースの予想・検証の依頼なら、必ず /haruto-jra-forecast スキルを起動し、
haruto/MASTER_PROMPT.md（V19）を最終行まで全文読み、専門エージェント（.claude/agents/haruto-*）を
Agent ツールで実際に起動して全22PHASE・14担当・TRIPLE CHECK・最終監査・note版まで実行すること。
未取得・未実行は明記し、捏造・後知恵は禁止。競馬と無関係・地方競馬(NAR)の依頼ならこの注意は無視してよい。
MSG
fi
exit 0
