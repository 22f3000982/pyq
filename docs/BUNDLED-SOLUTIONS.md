# Bundled paper solutions

Admin → Solutions: use course/exam and coverage filters, select up to five papers with checkboxes, then **Export selected bundle**.

Unzip the download. Give the AI `questions.json`, the included PDFs, and `BUNDLE_PROMPT.txt`. PDFs that cannot be retrieved are listed in README; attach those originals separately. The AI must return one JSON object:

```json
{"format":"pyq-solutions-bundle-v1","papers":[{"format":"pyq-solutions-v1","paper_id":123,"solutions":[{"question_id":456,"version":"exact exported version","output":{"final_answer":["A"],"explanation":"Reasoning","option_explanations":{"A":"Correct","B":"Incorrect"},"needs_review":false}}]}]}
```

Paste or upload that single JSON (up to 8 MB), click **Preview bundle**, inspect each paper, then **Save & Publish valid solutions**. Enable overwrite only when replacing included question solutions. Omitted solutions remain unchanged. An invalid paper is skipped entirely; its error is shown while valid papers can be saved. Answer-key/format warnings remain unpublished for review. These checks do not verify reasoning correctness.

Single-paper import remains available. Bundle routes require admin login and imports require CSRF protection. This is an admin-only operation and adds no student requests or schema migrations. ZIP PDFs are capped at 100 MB total; no new files are stored in R2 by export. Cloud PDFs may populate the existing local asset cache.
