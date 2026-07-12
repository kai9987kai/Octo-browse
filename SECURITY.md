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

- Python plugins and the extension lab are trusted local automation, not a
  sandbox. They are disabled by default behind an explicit Developer Mode.
- The trusted extension action intentionally preserves the original prototype's
  full Python execution behavior. Treat it as local code execution.
- API keys use the operating-system credential vault through `keyring` when a
  backend is available. The app retains a JSON fallback for unsupported source
  environments and reports this limitation in the README.
- Private tabs use an off-the-record Qt profile, but the application has not
  undergone a full privacy/security audit.
- Read Aloud uses the cloud-based Google Text-to-Speech service. Private-page
  text requires confirmation on each use; generated audio is temporary.
- Release binaries are not Authenticode-signed by default. Verify published
  artifacts against `SHA256SUMS.txt`; SmartScreen trust requires a separately
  configured signing certificate.
- The ad blocker implements a tested EasyList subset, including resource-type
  and first/third-party semantics, but is not a full uBlock Origin replacement.
