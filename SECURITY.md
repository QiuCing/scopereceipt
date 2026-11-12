# Security considerations

This is a prototype, not a secure monitoring appliance.

- It deliberately makes **no claim of observing tools other than its own tracked reads**.
- It does **not** verify semantic comprehension or human-like attention.
- Local JSON receipts are not signed or secured against a process with write access.
- Avoid publishing `.scopereceipt/`: it contains absolute input paths and filenames.
- Archive parsing is bounded and does not extract ZIP files, but processing untrusted PDFs still requires patched PyMuPDF versions and normal OS sandboxing.
- Processing documents does not grant permission to publish them. Use synthetic fixtures for public demos.

For a security issue, report privately to the repository maintainer after publication. Do not publish vulnerability proof-of-concept data that reveals user documents.
