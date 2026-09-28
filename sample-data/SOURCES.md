# Supplied sources

- `catalog.xlsx`: identical copy of the user's Degree Question Papers workbook, SHA-256 cd18e10f532fe5e7d75f15c9b584df8dd4e342e4459d323fadd4d10d683eeaa7. It is the authoritative paper catalog, not a question bank.
- `software-testing-may-2026-quiz1.pdf`: retrieved through the workbook's May 2026 sheet, F5, Software Testing, Quiz 1. Original: https://drive.google.com/file/d/1E-MmzBaggBUJMfXifzRTDhNyFaMD2DJ2/view . Ten pages, 21 numbered items (the header counts grouped questions differently). Item 1 is a zero-mark subject-confirmation prompt, not a substantive PYQ. Several other items contain image-only notation/options and are preserved as structured question images where extractable. No affiliation or ownership claim is made.

The parser extracts 21 records automatically, including the instruction item. The zero-mark instruction is excluded from student practice. Twenty scored items become available automatically when validation succeeds. No verified exam duration was established from this source.

Tests construct clearly marked DEMO DATA only in temporary test databases. Demo fixture answers are synthetic test specifications, not claimed PYQs.

## Five-paper student demonstration

- Deep Learning / End Term FN / May 2026: https://drive.google.com/file/d/1fOY2d4kCfVGlkmn1VQ4Je66kEa-hDIKG/view?usp=sharing
- Software Engineering / Quiz 2  / May 2026: https://drive.google.com/file/d/1B4rqkE5mn-pleKeVmF8taJcU7Mi95KHe/view?usp=sharing
- Game Theory and Strategy / Quiz 1  / May 2026: https://drive.google.com/file/d/1TiJdF354Xwl79eornLLxmGtXydBP2egm/view?usp=sharing
- Managerial Economics / Quiz 1  / May 2026: https://drive.google.com/file/d/1dYnI8qFqiNpHx9U3HX5l5x0QuwdCxyZ6/view?usp=sharing
- AI: Search Methods for Problem Solving / Quiz 1  / May 2026: https://drive.google.com/file/d/1Grn4wv3Qj6tbWUVBAKGoFGrFM6zGyYyh/view?usp=sharing

`five-papers.json` maps each included PDF to its Excel catalog paper ID. The older Software Testing source is retained only as a regression test fixture; it is not a sixth student paper in the delivered snapshot.
