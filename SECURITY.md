# Security Policy

Octo-browse is an experimental desktop browser prototype. Please report
security problems privately rather than opening a public issue with exploit
details.

## Supported Versions

Only the current `main` branch is supported for security fixes.

## Reporting a Vulnerability

Report suspected vulnerabilities to the repository owner using a private
GitHub security advisory if available, or by direct private contact if this is
a fork without advisories enabled.

Please include:

- A short description of the issue.
- Steps to reproduce.
- Impact, including whether local file access, command execution, credential
  exposure, or browsing-data exposure is involved.
- Relevant OS, Python, PyQt6, and PyQtWebEngine versions.

## Known Prototype Risks

- The extension lab runs user-provided Python in a constrained namespace, but
  it is not a hardened sandbox.
- The trusted extension action intentionally preserves the original prototype's
  full Python execution behavior. Treat it as local code execution.
- Settings API keys are stored in local JSON when entered through the app.
- Private tabs use an off-the-record Qt profile, but the application has not
  undergone a full privacy/security audit.
- The ad blocker is a small static blocklist and does not implement full
  browser-grade filter rules.
