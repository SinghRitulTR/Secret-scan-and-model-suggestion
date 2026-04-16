"""PreToolUse hook: block broad git add commands (git add . / git add -A)."""
import json
import sys

def main():
    input_data = json.loads(sys.stdin.read())
    tool_input = input_data.get("tool_input", {})
    command = tool_input.get("command", "")

    blocked_patterns = ["git add .", "git add -A", "git add --all"]
    for pattern in blocked_patterns:
        if pattern in command:
            print(json.dumps({
                "decision": "block",
                "reason": f"Blocked broad staging command '{pattern}'. Stage specific files instead."
            }))
            return

    print(json.dumps({"decision": "approve"}))

if __name__ == "__main__":
    main()
