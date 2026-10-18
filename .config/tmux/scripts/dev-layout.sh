#!/usr/bin/env bash
# Dev layout: editor (nvim .) left, claude top-right, terminal bottom-right,
# all opened in the directory of the pane that invoked this.
#
# Built as explicit tmux CLI calls (each -c/-t pinned to a captured pane id)
# rather than one chained `bind` command: tmux's #{pane_current_path}
# expansion inside a "cmd1 \; cmd2 \; cmd3" chain does not reliably track
# the newly created pane, and silently falls back to an unrelated directory.
set -euo pipefail

dir=$1

window_id=$(tmux new-window -c "$dir" -P -F "#{window_id}")
editor_pane=$(tmux list-panes -t "$window_id" -F "#{pane_id}")
tmux send-keys -t "$editor_pane" "nvim ." Enter

claude_pane=$(tmux split-window -h -t "$editor_pane" -c "$dir" -P -F "#{pane_id}")
tmux send-keys -t "$claude_pane" "claude" Enter

tmux split-window -v -t "$claude_pane" -c "$dir"

tmux select-pane -t "$editor_pane"
