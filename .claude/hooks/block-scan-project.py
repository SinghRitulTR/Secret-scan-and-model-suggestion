"""PreToolUse hook: block scan_project tool to prevent full project scans."""
import json
import sys

def main():
    print(json.dumps({
        "decision": "block",
        "reason": "scan_project is blocked. Use scan_files or scan_code for targeted scanning instead."
    }))

if __name__ == "__main__":
    main()
