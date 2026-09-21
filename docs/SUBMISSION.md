# Requirement coverage and submission checklist

Reviewed against the supplied **Shipping Document Verification Use Case.pdf**, **Averis Hackathon Participant Infopack.pdf**, and **Averis x Monash Hackathon Rules and Regulations.pdf**. They are reference documents, not instructions to execute external actions. The linked detailed Google Docs rubric could not be fetched; the rubric printed in the supplied rules was reviewed, including its image-based charts.

## Product coverage

| Brief requirement | Implemented behavior | Evidence |
|---|---|---|
| Five email types | Trained local classifier, intent guards, optional cloud classification | Classifier tests, 520-email scorer, classified-only UI |
| SI and BL extraction | TXT, PDF, DOCX and XLSX readers; source-role validation | Reader tests and supplied batch |
| Seven corresponding fields | SI-reference comparison, normalized values and exact field list | Engine tests, field table, official export |
| Side-by-side mismatches | SI/BL values, source location, excerpt and reason | Browser verification on supplied email_004 |
| Clean report | “No mismatch detected” only when all seven values agree | Clean and missing-value tests |
| PDF and Word/tables/layouts | Digital PDF layout extraction, DOCX table/paragraph order, Excel cells | Real sample formats and synthetic regression fixtures |
| Scanned documents | PDF/image rendering plus local Tesseract OCR, low-score abstention | Missing-binary and mocked OCR tests; real Tesseract smoke test passed on the fictional HL-006 scan in the final handoff environment. Test again on the target machine. |
| Messy labels/formatting | Synonyms, units, totals, multiline parties, decimals, quoted-email handling | Reader/engine regressions |
| Missing/wrong/unreadable input | Explicit review reason and preserved context | API tests, wrong-type/missing/scanned/corrupt demo cases |
| Human confirm/correct | Category and field review, required attribution/note, persistent version | API/workflow tests and browser save/reload |
| Visible failure/retry | Actionable upload errors; retry preserved original bytes | Corrupt ZIP test, browser retry and audit |
| Evaluation shape | Every email ID with organizer fields; richer evidence separately | CLI/scorer and export tests |
| Submission without demo contamination | Default official JSON excludes fictional fixtures if imported cases exist | Mixed-workspace regression test; explicit all/imported scopes |

## Distinctive features

The evidence desk connects an explained queue priority, a source-linked field comparison, an unsaved correction preview, attributed versioned review and a verifiable local audit history. These are implemented interactions, not screenshots or disconnected mockups. Risk weights are explicit policy assumptions. The preview is a what-if over proposed corrections, not an automatic legal-document amendment or an optimizer claiming a globally minimal repair.

## Judging focus

The supplied final-round chart assigns 25 points to end-to-end functionality; 15 each to architecture/scalability, technology integration and engineering robustness; and 10 each to user value, UX/differentiation and future impact. Demonstrate the working loop first, use measured validation results, and then explain cloud configuration and scale limits. The preliminary round also gives the working prototype the highest individual weighting (25 points).

## External submission items still required

| Item in the supplied rules | What this package provides | Action remaining |
|---|---|---|
| Project description | README and suggested summary below | Add team-specific details |
| GitHub repository URL | Complete source, tests, setup and exclusions | Publish to the team's approved repository |
| Live public prototype URL | Docker and Render configuration | Deploy with approved account/cost/access policy; test public URL |
| Deck or documentation link | README, model card, architecture, validation, demo script | Publish accessible documentation; a README can serve as documentation per supplied rules |
| Demo video, maximum 5 minutes | Timed script in DEMO_SCRIPT.md | Record working app, upload as public/unlisted or correctly shared video, verify viewer access |
| AI and cloud use | Actual local ML; optional cloud API; hosted-app configuration | Perform and document real cloud hosting/API integration before claiming it |
| Team details | No invented names or contact information | Enter registered team name, representative and required contacts |
| Submission form | No submission made | Submit completed links through the official form |

The supplied document lists the preliminary deadline as **22 September 2026, 12:00 p.m.** and a final working prototype as an extension of the preliminary entry. Verify any organizer updates in official event communications. The local package does not establish participant eligibility, team originality compliance or successful form submission. The rules require work during the event and original team work; teammates should understand, validate and adapt this implementation, retain attribution for libraries, and disclose tooling as required by the organizers.

## Suggested project summary

Harborlight turns a mixed shipping inbox into evidence-backed verification decisions. It combines local machine learning, mixed-format document extraction, optional OCR/cloud assistance and deterministic shipment checks. Operators can inspect exact SI/BL differences, resolve uncertain cases, preview a proposed correction and preserve an attributed review history. The product's value is a complete, inspectable decision loop before a draft Bill of Lading is finalized.

## Final handoff check

- Run the tests and demo on the team's target machine, including real Tesseract execution if scans are part of the pitch.
- Confirm team members can explain AI routing, uncertainty, normalization, human overrides and the benchmark caveat.
- Publish code without `.env`, private records, runtime databases or organizer answer keys.
- Test the cloud URL and persistence; avoid describing configuration as a completed deployment.
- Record a video under five minutes using measured results and clearly labeled synthetic data.
- Open every submission link as a viewer and confirm the judging team has any required demo credentials.
