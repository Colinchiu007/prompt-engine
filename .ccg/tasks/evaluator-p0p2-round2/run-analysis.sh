#!/bin/bash
cd /d/Data/projects/mp-worktrees/pe-round3bc-delivery
export CLAUDE_CODE_GIT_BASH_PATH='D:/Program Files/Git/usr/bin/bash.exe'
TASK=.ccg/tasks/evaluator-p0p2-round2/analysis-task.md
WRAPPER='C:/Users/邱领/.claude/bin/codeagent-wrapper.exe'
{
  cat "$TASK" | "$WRAPPER" --backend antigravity --progress - . > .ccg/tasks/evaluator-p0p2-round2/analysis-antigravity.md 2>&1
} &
{
  cat "$TASK" | "$WRAPPER" --backend claude --progress - . > .ccg/tasks/evaluator-p0p2-round2/analysis-claude.md 2>&1
} &
wait
echo "ALL_DONE"
