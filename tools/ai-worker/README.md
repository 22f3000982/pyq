# Local AI solution worker (Windows)

After deployment, use **Admin → AI Solutions**. Your PC runs generation; Render only queues jobs and serves saved text.

1. Install Python 3. Download/clone this repository, open `tools/ai-worker`, and double-click `SETUP_AI_WORKER.cmd` once.
2. Edit the created `local.env`: set `GEMINI_API_KEY`, `GEMINI_MODEL`, and `PYQ_ADMIN_EMAIL`. Confirm free API quota in your Google AI Studio project before setting `GEMINI_FREE_TIER_CONFIRMED=yes`. A Gemini subscription and API billing are separate; this flag is your acknowledgement, not an automated billing check. No paid fallback is configured.
3. Double-click `START_AI_WORKER.cmd`. Enter your existing website admin password in the hidden prompt. No Supabase credential is needed. The Gemini key stays on your PC and goes only to Google.
4. On the website select a course/paper, then **Generate 5 samples**. Review them, then use **Generate full paper** to queue all missing solutions for the selected paper in one click. Existing current solutions and already queued questions are skipped; filters and selected checkboxes do not limit this full-paper action. Select specific questions, regenerate failures, or pause/resume batches. The worker processes one question at a time with a minimum 10-second pause.
5. **Preview / edit** shows the question, key and solution. `CHECKS PASSED` means source-key consistency and structure checks passed; it does not certify correct reasoning. Flagged solutions require manual editing before publication. Save a draft, then publish individually or select drafts to publish together.
6. Practice **Check answer** loads published explanations; exam mode permits them only after submission. Source keys and scoring rules stay unchanged. A changed question hides its old solution until regeneration and publication.
7. Ctrl+C stops safely. Jobs stay queued offline; abandoned jobs recover after a 10-minute lease. Quota/auth failures pause the batch: fix the key/model or wait for reset, then Resume. Temporary failures retry three times. Restart and sign in again if the admin session expires.

`local.env` and the virtual environment are ignored by Git. Never share keys or that file. Render does not need Gemini keys for this feature. Groq/OpenRouter are not used in this version.

Deployment adds three tables using the existing migration flow. One solution and one current job are stored per question, without accumulating solution revisions. Text is bounded to 14,000 characters. Start Exam carries no solution payload and invokes no AI. Check answer adds a saved-text read; worker traffic still shares the database, so run small batches outside peak exam times if necessary.
