# Jason Jones Resume

Refreshed resume package optimized for ATS parsing and visual presentation.

## Files

| File | Use case |
|------|----------|
| `Jason_Jones_Resume_ATS.docx` | **Primary upload file** for job applications and ATS portals |
| `Jason_Jones_Resume_ATS.txt` | Plain-text fallback for systems that only accept `.txt` |
| `Jason_Jones_Resume_Visual.pdf` | Networking, email attachments, and human reviewers |
| `Jason_Jones_Resume_Visual.html` | Browser preview; print to PDF if needed |

## ATS optimizations

- Single-column layout with standard section headers
- No tables, text boxes, icons, or graphics
- Calibri font (widely ATS-compatible)
- Full URLs (`https://`) for GitHub and portfolio links
- Keyword-rich Core Skills section placed high on the document
- Consistent date format and bullet structure
- Location set to **Sioux Falls, SD**

## Regenerate

```bash
python3 resume/generate_resume.py
```
