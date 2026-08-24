#!/usr/bin/env bash
# Eval suite runner: executes a task suite headlessly against an opencode agent.
#
# Usage:
#   ./eval/run_suite.sh --agent NAME [options]
#
# Options:
#   --agent NAME        agent id (file .opencode/agents/NAME.md)   [required]
#   --suite DIR         task suite dir (default: eval/tasks/default)
#   --backend WHICH     auto | ollama | lmstudio | none   (default: auto)
#                       auto  = probe endpoints, use first live one (warm-up included)
#                       none  = skip warm-up entirely (e.g. cloud model)
#   --model P/M         override model (default: whatever the agent file pins)
#   --out DIR           results dir (default: eval/results/<ts>-<agent>)
#   --timeout SEC       per-task timeout (default: 300)
#   --keep              keep task sandbox dirs (debugging)
#   --label LBL         label stored in scores.json (default: out dir basename)
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

AGENT="" SUITE="$HERE/tasks/default" BACKEND="auto" MODEL="" OUT="" TIMEOUT=300 KEEP=0 LABEL=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --agent)   AGENT="$2"; shift 2 ;;
    --suite)   SUITE="$2"; shift 2 ;;
    --backend) BACKEND="$2"; shift 2 ;;
    --model)   MODEL="$2"; shift 2 ;;
    --out)     OUT="$2"; shift 2 ;;
    --timeout) TIMEOUT="$2"; shift 2 ;;
    --keep)    KEEP=1; shift ;;
    --label)   LABEL="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done
[[ -z "$AGENT" ]] && { echo "--agent is required" >&2; exit 2; }
[[ -d "$SUITE" ]] || { echo "suite dir not found: $SUITE" >&2; exit 2; }
command -v opencode >/dev/null || { echo "opencode not on PATH" >&2; exit 2; }
command -v jq >/dev/null     || { echo "jq not on PATH" >&2; exit 2; }

# Resolve the model the run will actually use: --model flag wins, else agent frontmatter.
AGENT_FILE=""
for cand in ".opencode/agents/$AGENT.md" "$HOME/.config/opencode/agents/$AGENT.md"; do
  [[ -f "$cand" ]] && { AGENT_FILE="$cand"; break; }
done
PINNED_MODEL="${MODEL:-$(sed -n 's/^model:[[:space:]]*["'\'']\{0,1\}\([^"'\''#]*\)["'\'']\{0,1\}.*/\1/p' "$AGENT_FILE" 2>/dev/null | head -1)}"

TS="$(date +%Y%m%d-%H%M%S)"
OUT="${OUT:-$HERE/results/$TS-$AGENT}"
LABEL="${LABEL:-$(basename "$OUT")}"
PROJECT_ROOT="$(dirname "$HERE")"
mkdir -p "$OUT"

echo "agent=$AGENT suite=$SUITE backend=$BACKEND out=$OUT"

# ── backend detection + warm-up ────────────────────────────────────────────────
WARM_URL=""
if [[ "$BACKEND" != "none" ]]; then
  while IFS=$'\t' read -r name base; do
    if curl -sf --max-time 4 "$base/models" >/dev/null 2>&1; then
      # explicit --backend: match it; auto: prefer the endpoint serving the pinned model
      if [[ "$BACKEND" == "$name" ]]; then WARM_URL="$base"; break; fi
      if [[ "$BACKEND" == "auto" ]] && [[ "$PINNED_MODEL" == "$name/"* ]]; then WARM_URL="$base"; break; fi
      [[ "$BACKEND" == "auto" && -z "$WARM_URL" ]] && WARM_URL="$base"
    fi
  done < <(jq -r '[.profiles[].endpoints[]] | unique_by(.backend)[] | [.backend, .baseURL] | @tsv' "$HERE/backends.json")
  if [[ "$BACKEND" != "auto" && -z "$WARM_URL" ]]; then
    echo "ERROR: requested backend '$BACKEND' is not reachable." >&2; exit 3
  fi
  if [[ -n "$WARM_URL" ]]; then
    # Pre-warm the EXACT model that will serve (JIT backends pay disk-load latency on first call).
    # Never warm .data[0] blindly — endpoints often list embedding models first.
    warm_model="${PINNED_MODEL#*/}"
    if [[ -z "$warm_model" || "$warm_model" == "$PINNED_MODEL" ]] || \
       ! curl -sf --max-time 5 "$WARM_URL/models" | jq -e --arg m "$warm_model" '.data[]?.id == $m' >/dev/null; then
      warm_model=$(curl -sf --max-time 5 "$WARM_URL/models" \
        | jq -r '[.data[]?.id // empty
                  | select(test("embed|minilm|bge|gte|e5[-_]|rerank";"i") | not)][0] // empty')
    fi
    echo "warming up $WARM_URL (model: ${warm_model:-any})"
    curl -s --max-time 180 "$WARM_URL/chat/completions" -H 'Content-Type: application/json' \
      -d "{\"model\":\"${warm_model:-}\",\"messages\":[{\"role\":\"user\",\"content\":\"ping\"}],\"max_tokens\":5}" >/dev/null 2>&1 || true
  fi
fi

# ── run tasks ──────────────────────────────────────────────────────────────────
shopt -s nullglob
TASKS=("$SUITE"/T*.json)
((${#TASKS[@]})) || { echo "no T*.json tasks in $SUITE" >&2; exit 2; }

for tf in "${TASKS[@]}"; do
  tid=$(jq -r '.id' "$tf")
  tier=$(jq -r '.tier' "$tf")
  prompt=$(jq -r '.prompt' "$tf")
  tdir=$(mktemp -d "/tmp/openeval.XXXXXX")
  # Project-scoped agents/config must be visible inside the sandbox project.
  ln -sfn "$PROJECT_ROOT/.opencode" "$tdir/.opencode"
  mkdir -p "$OUT/$tid"
  echo "── [$tier] $tid  (sandbox: $tdir)"

  # setup
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    ( cd "$tdir" && eval "$line" ) >>"$OUT/$tid/setup.log" 2>&1 || echo "SETUP FAILED: $line" >>"$OUT/$tid/setup.log"
  done < <(jq -r '(.setup // [])[]' "$tf")

  # timed run
  args=(run --dir "$tdir" --agent "$AGENT" --auto --format json
        --title "eval:$AGENT:$tid" ${MODEL:+--model "$MODEL"})
  t0=$(date +%s%N)
  timeout "$TIMEOUT" opencode "${args[@]}" "$prompt" >"$OUT/$tid/raw.jsonl" 2>"$OUT/$tid/stderr.log"
  rc=$?
  t1=$(date +%s%N)
  python3 -c "print($t1-$t0)" > "$OUT/$tid/wall_ns"

  # extract sessionID for full-trace export (raw events → title lookup fallback)
  sid=$(jq -r 'select(.type? == "session.idle" or .sessionID?) | .sessionID // empty' "$OUT/$tid/raw.jsonl" 2>/dev/null | tail -1)
  [[ -z "$sid" ]] && sid=$(grep -o '"sessionID":"[^"]*"' "$OUT/$tid/raw.jsonl" 2>/dev/null | head -1 | cut -d'"' -f4)
  [[ -z "$sid" ]] && sid=$(opencode session list --format json --max-count 30 2>/dev/null \
    | jq -r --arg t "eval:$AGENT:$tid" '[.[] | select((.title // .id // "") | contains($t))][0].id // empty')
  if [[ -n "$sid" ]]; then
    opencode export "$sid" >"$OUT/$tid/trace.json" 2>/dev/null || true
    printf '%s' "$sid" > "$OUT/$tid/session_id"
  fi

  echo "rc=$rc sid=${sid:-none} wall=$(python3 -c "print(round(($t1-$t0)/1e9,1))" 2>/dev/null)s"
  # Snapshot the sandbox into the run dir so file_* checks survive cleanup.
  mkdir -p "$OUT/$tid/sandbox"
  cp -a "$tdir/." "$OUT/$tid/sandbox/" 2>/dev/null || true
  [[ "$KEEP" == "1" ]] || rm -rf "$tdir"
done

# ── score ──────────────────────────────────────────────────────────────────────
python3 "$HERE/score.py" --out "$OUT" --suite "$SUITE" --label "$LABEL" \
  ${MODEL:+--model "$MODEL"} ${WARM_URL:+--backend-url "$WARM_URL"}
echo "scores → $OUT/scores.json"
