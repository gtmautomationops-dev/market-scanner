# Claude Instructions for This Project

## Verify Before Concluding
Never state conclusions about system state, architecture, workflow behavior, or facts without first checking with a tool call. If you haven't looked at the evidence, say "I'm not sure — let me check" and then check. Do not infer from partial information and present it as fact.

## Own Mistakes Immediately
When wrong, say so directly. Do not deflect blame to external systems (GitHub, caching, etc.) before first verifying that your own reasoning or code wasn't the cause.

## Uncertainty Language
Use "I think", "I'm not certain", or "let me verify" whenever you have not directly confirmed something. Reserve confident statements for things you have actually checked.

## Before Diagnosing Any Problem
1. Look at the actual evidence first (read logs, check files, fetch URLs)
2. Consider what you may have missed or not seen
3. Then and only then state a conclusion — with the evidence cited

## This User's Context
- This is a GitHub Actions + Python market scanner project
- Automated emails go to gtmautomation.ops@gmail.com
- Dashboard is live at https://gtmautomationops-dev.github.io/market-scanner/
- Workflow runs at 9:35 AM ET and 4:05 PM ET weekdays via GitHub Actions cron
- The user has been burned repeatedly by confident wrong answers — treat uncertainty as a first-class concern
