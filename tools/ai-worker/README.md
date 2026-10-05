# Local multi-provider worker — Windows
1. Stop old worker (Ctrl+C), extract ZIP into a new folder, open ai-worker.
2. Run SETUP_AI_WORKER.cmd. Python 3 required. Edit created local.env in Notepad.
3. Enter PYQ_ADMIN_EMAIL and your API keys. Keep local.env private; quotes normally unnecessary. Do not save as local.env.txt. Do not add your admin password.
4. Google free project: GEMINI_FREE_TIER_CONFIRMED=yes. Antigravity uses the SAME Google key: ANTIGRAVITY_ENABLED=yes. Groq free account: GROQ_FREE_TIER_CONFIRMED=yes. These acknowledgements do not verify provider billing. Enable only confirmed free accounts/projects.
5. Run START_AI_WORKER.cmd; type admin password at hidden prompt.
6. Website Admin > AI Solutions: pause unrelated batches and resume ONE small paper. Do not regenerate existing solutions. Failed questions need separate requeue via pending-solution generation.
7. Inspect terminal and preview solutions. DONE means saved draft, not published. Share only Job/Fallback lines, NEVER local.env or keys.

The worker runs locally against the deployed website. No full local website setup required. All provider keys stay on PC; Render keys are not automatically available. It processes one question at a time, leaves answer keys/questions unchanged and preserves original image quality.

Default order groq,gemini,antigravity,openrouter. Missing providers are skipped. For isolated tests set AI_PROVIDER_ORDER=groq, then optionally test each other provider individually. Groq text: openai/gpt-oss-120b. Groq vision: qwen/qwen3.8-27b (maximum 3 images); excess images skip Groq, never drop images. Other adapters receive all images. OpenRouter routing receives image inputs; incompatible output falls back.

Only openrouter/free or :free IDs allowed, with zero prompt/completion price constraints. There is no paid fallback. Provider quotas still apply. Google/Groq free-tier flags are acknowledgements, not automated billing checks. No guarantee of correctness or daily throughput.

429 cools that provider for 15 minutes in the current process; server/network/invalid output for 60 seconds; auth/config disables it for current process (restart after correcting settings). If all compatible providers are unavailable, batch safely pauses with queued job preserved. Resume manually when quota available. 15 minutes does NOT mean daily quota resets then. Model/token/day limits can exhaust before request/day limits.

Missing, oversized or unsupported source images fail explicitly; signed-image HTTP failures try authenticated proxy. No images silently omitted. Output is checked locally and validated on server; source answer keys remain authoritative for scoring. Preview before publish.

Mock adapter/fallback/security tests pass. Live API calls with your credentials have NOT been tested here. Antigravity preview/API configuration and OpenRouter free availability may change. Before deployment, admin error/provider metadata may remain generic/Gemini; use terminal for actual provider. server-update-source contains pending app source changes for reference, not files to copy into the worker folder. No GitHub push has been made.
