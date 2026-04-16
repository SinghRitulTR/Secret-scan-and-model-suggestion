#!/usr/bin/env node
/** PreToolUse hook: block broad git add commands (git add . / git add -A). */

let input = '';
process.stdin.on('data', chunk => { input += chunk; });
process.stdin.on('end', () => {
  try {
    const data = JSON.parse(input);
    const command = (data.tool_input || {}).command || '';
    const blocked = ['git add .', 'git add -A', 'git add --all'];
    for (const pattern of blocked) {
      if (command.includes(pattern)) {
        console.log(JSON.stringify({
          decision: 'block',
          reason: `Blocked broad staging command '${pattern}'. Stage specific files instead.`
        }));
        process.exit(0);
      }
    }
    console.log(JSON.stringify({ decision: 'approve' }));
  } catch {
    console.log(JSON.stringify({ decision: 'approve' }));
  }
});
