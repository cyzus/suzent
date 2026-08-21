# Security Policy

## Supported Versions

SUZENT is pre-1.0 and moves quickly. Security fixes land on the latest stable release only.

| Version | Supported |
|---|---|
| Latest stable release | ✅ |
| `main` (development) | ✅ Best effort |
| Older releases | ❌ |

Run `suzent check-update` to see whether you are on the current release, and `suzent update` to move to it.

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues, pull requests, or Discord.**

Report privately through GitHub Security Advisories:

1. Go to the [Security tab](https://github.com/cyzus/suzent/security/advisories/new).
2. Click **Report a vulnerability**.
3. Describe the issue with enough detail to reproduce it.

This creates a private channel visible only to the maintainers.

### What to include

- The type of issue (sandbox escape, credential disclosure, command injection, permission bypass, and so on).
- Affected version, operating system, and configuration.
- Step-by-step reproduction, ideally with a minimal case.
- Impact: what an attacker gains, and what access they need to start.
- Any proof-of-concept, log excerpt, or patch you already have.

Please redact your own API keys, tokens, and personal data from anything you attach.

### What to expect

- **Acknowledgement** within 5 business days.
- **Initial assessment**, including whether we consider it in scope, within 10 business days.
- **Progress updates** as the fix develops.
- **Credit** in the release notes and advisory, unless you prefer to stay anonymous.

SUZENT is maintained by a small team. Timelines are targets, not guarantees.

## Scope

### In scope

- Sandbox escape: agent-executed code reaching outside its Docker workspace or configured path restrictions.
- Bypass of the tool-approval and permission system, including via prompt injection from untrusted content the agent reads.
- Disclosure of credentials — `.env` contents, provider API keys, messaging tokens — through logs, the UI, sync, or telemetry.
- GitHub Sync leaking device-local secrets into the synced repository.
- Access-control failures in messaging channels, such as an unlisted user reaching an agent through `allowed_users`.
- Remote code execution, authentication bypass, or SSRF in the local backend or desktop app.
- Supply-chain issues in the install and update path, including signature or integrity verification failures.

### Out of scope

- The agent executing actions the operator explicitly authorized. Approved tool calls doing exactly what they were approved to do is the intended design, not a vulnerability.
- Running SUZENT with permission checks disabled, sandboxing turned off, or a deliberately permissive configuration.
- Model output quality: hallucination, refusal, bias, or otherwise unhelpful answers.
- Vulnerabilities in third-party model providers, messaging platforms, or the operating system — report those to the vendor.
- Findings that require an attacker to already have local user or root access to the machine running SUZENT.
- Automated scanner output without a demonstrated, reachable impact.

## Safe Harbor

We will not pursue or support legal action against researchers who, in good faith:

- Test only against their own installation.
- Avoid privacy violations, data destruction, and service degradation.
- Give us reasonable time to remediate before public disclosure.

## Disclosure

We aim to publish an advisory and a fixed release together, and to coordinate timing with you. Please keep the details private until the fix ships.
