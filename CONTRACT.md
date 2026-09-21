# Harborlight internal integration contract

All app data is JSON-compatible. Runtime never reads organizer answer keys or generators.

## readers.py (document agent)
`read_document(data: bytes, filename: str, ocr: bool = True) -> dict`
returns `{filename, kind: SI|BL|OTHER|UNKNOWN, text, pages:[{page:int,text:str,method:str}], fields:{field:{value:str|null, evidence:str, page:int, confidence:float, method:str}}, warnings:[str], error:str|null, sha256:str}`.
All seven fields keys when possible. Includes deterministic evidence-linked label extraction. Errors are visible. OCR optional Tesseract CLI; no cloud requests here.

## engine.py (engine agent)
`FIELDS`, `CATEGORIES` constants.
`analyze(email:dict, documents:list[dict], use_ai:bool=False) -> dict`.
`classify(email:dict) -> dict {category,confidence,method,reason,scores}`.
`compare(si:dict, bl:dict) -> list[dict]` seven rows `{field,si,bl,si_normalized,bl_normalized,outcome:match|mismatch|uncertain,reason,si_evidence:dict,bl_evidence:dict}`; si/bl are reader document dicts.
analyze returns `{email_id,category,status:OK|MISMATCH|NEEDS_REVIEW,review_reason:null|wrong_doc_type|missing_attachment|unreadable|missing_value,has_defect:bool,defect_fields:[],classification:{...},rows:[],reasons:[],summary:str,risk_score:int,documents:[],ai:{...}}`. Root adds persisted id, email, created_at, version, audit.
Classifier uses actual local ML trained only on independently authored examples, plus transparent routing signals. Optional cloud AI must not silently masquerade as used.

## HTTP API (root)
GET /api/health -> {status,version,ai,ocr}
GET /api/cases -> {cases:[report summaries/full reports],stats:{total,clean,mismatches,review,classified,reviewed},audit_valid:bool}
GET /api/cases/{id} -> full report + email + audit + version
POST /api/demo -> seed/analyze bundled curated demo (no external send)
POST /api/import -> multipart `files` repeated: ZIP bundle OR email JSON and attachments; optional use_ai form boolean. -> {processed,errors:[],cases:[]}
POST /api/cases/{id}/retry -> {use_ai:bool} -> full report
POST /api/cases/{id}/simulate -> {corrections:{si:{field:value},bl:{field:value}}} -> {before:report,after:report,changes:[],persisted:false}
POST /api/cases/{id}/review -> {version:int,reviewer:str,note:str,corrections:{si:{field:value},bl:{field:value}},decision:confirm|correct} -> report; conflict 409
GET /api/export/submission -> official JSON keyed by email id
GET /api/export/report -> full reports JSON
GET /api/export/csv -> flat discrepancy CSV
GET /api/cases/{id}/attachments/{index} -> source download
GET /api/audit -> {events:[],valid:bool}
All POST JSON except import; API errors `{detail:...}`. UI uses same origin, safe DOM text (no untrusted innerHTML), responsive vanilla JS. Repeated demo/import replaces by email id and preserves audit.

Use SI as reference; never treat missing as a mismatch. Never rewrite original source. Review correction can update extracted values only with preserved evidence/provenance. Scoring export strips extended fields. No automatic outgoing emails or real shipment approvals.
