# HackTheAI — Asterion Protocol

![Python 3.13+](https://img.shields.io/badge/Python-3.13%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?logo=fastapi&logoColor=white)
![20 challenges](https://img.shields.io/badge/Challenges-20-14b8a6)
![30 prompts per challenge](https://img.shields.io/badge/Prompts-30%20per%20challenge-0ea5e9)
![Docker](https://img.shields.io/badge/Container-Docker-2496ED?logo=docker&logoColor=white)
![Groq live mode](https://img.shields.io/badge/Live%20AI-Groq-f55036)

A single-player orbital hacking puzzle for people who enjoy prompt injection, AI agents, and figuring out where trust breaks. Outsmart twenty fictional guards aboard **Asterion**, uncover a recovery signature, and find your way home.

Each station has a friendly AI guard, a distinct defense, a computing topic, and an intended recovery method. Guards explain and coach, but ordinary requests for the protected value do not unlock a station. Players must experiment with the station's simulated trust boundary.

The application runs as a single FastAPI service with a plain HTML/CSS/JavaScript frontend. **No frontend build is required.** Live conversations use Groq; offline demonstrations and the separate practice lab work without an API key.

[Quick start](#quick-start) · [Challenges](#the-twenty-challenges) · [Configuration](#configuration) · [Northflank deployment](#northflank-deployment) · [Security](#security-and-privacy) · [Testing](#development-and-testing)

## What you get

- Cinematic orbital artwork, individual station icons, responsive layouts, and a mission progress indicator.
- Twenty sequential challenges covering prompt injection, retrieval, tools, memory, agent handoffs, and OAuth concepts.
- Thirty AI prompts per challenge, progressive hints, station notes, conversation logs, and a maximum score of 200.
- Three mission starts per IP in total, enforced by a persistent SQLite ledger.
- An unlimited, isolated practice lab at /demo and a facilitator field guide at /guide.
- A defense workshop, downloadable PDF mission log, and completion certificate.
- A responsive orbital console with keyboard navigation, local fonts, reduced-motion support, and text-only rendering of untrusted content.
- Server-side secret generation, bounded provider spending, secure session cookies, and explicit reverse-proxy trust.
- A non-root Docker image and a Northflank infrastructure template with persistent quota storage.

This is a controlled educational simulation. Its systems, identities, documents, tools, and recovery values are fictional; it does not execute attacks against real infrastructure.

## Quick start

### Requirements

- Python 3.13 or newer.
- A modern browser.
- A Groq API key only for live mode.
- Node.js and npm only for frontend development checks and browser tests.
- Docker only for container-based execution.

### Windows / PowerShell

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe app.py
```

### Linux / macOS

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
.venv/bin/python app.py
```

Open **http://localhost:10000**. The example configuration starts the main mission in demo mode. PORT changes the listening port.

The helper in this prepared Windows workspace can also run Python with ./scripts/run-python.ps1 app.py. Its optional local runtime lives in the ignored .runtime directory; normal installations should use their own virtual environment.

### Enable live AI

Edit .env:

```dotenv
GAME_MODE=live
GROQ_API_KEY=your-own-groq-api-key
GROQ_MODEL=openai/gpt-oss-120b
MASTER_SECRET=your-own-random-secret-at-least-32-characters-long
PORT=10000
```

Generate a master secret locally:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Restart the server after changing configuration. Live mode refuses to start without an API key and a master secret of at least 32 characters. Environment variables supplied by your hosting platform take precedence over .env.

Keep .env private. The repository and Docker context exclude it and its local variants.

The local .env is a plaintext file, not encrypted storage. Never publish it or serve it
as a static asset. Only .env.example, with empty credential fields, belongs in Git.
For production, supply secrets through the hosting platform's private runtime
configuration. Run `python scripts/check-publication.py` before packaging; the
publication helper also checks the complete staged Git contents before committing.
The check detects local credential values and common token/private-key formats; it
does not audit Git history. If a credential was previously committed, revoke/rotate
it and remove it from repository history before making the repository public.

### Docker

```bash
docker build -t hacktheai .
docker volume create hacktheai-data
docker run --rm --name hacktheai -p 10000:10000 --env-file .env \
  --mount source=hacktheai-data,target=/app/.data hacktheai
```

In PowerShell, put the docker run command on one line or use PowerShell's line continuation.

Mount /app/.data to durable storage. The image runs as UID/GID 10001:10001 and listens on port 10000 by default. Its built-in health check requests /health. For local HTTP, keep SECURE_COOKIES=false; use true behind production HTTPS.

## Playing a mission

1. Choose a callsign and start a mission.
2. Read the current station's computing brief and the guard's stated defense.
3. Ask questions, test a prompt, or edit the provided document/log when that station requires source injection.
4. Inspect the response and any simulated execution trace. Decode reversed or Base64 values when appropriate.
5. Submit the complete recovery value if manual verification is required.
6. Record observations, recover the next station, and continue through all twenty.
7. Complete the optional defense workshop and download your mission log and certificate.

Use /demo before starting a scored mission. The practice lab has its own session, unlimited unscored experiments, baseline comparisons, hints, optional solution reveal, and an understanding check. Practice does not consume the three-start mission allowance.

### Rules and scoring

| Rule                  | Behavior                                                                      |
| --------------------- | ----------------------------------------------------------------------------- |
| Challenge count       | 20, unlocked in sequence                                                      |
| AI prompt allowance   | 30 per challenge; up to 600 per mission                                       |
| Prompt accounting     | Successful help/conversation responses count; provider failures do not        |
| Last prompt           | A successful 30th prompt counts; an unsuccessful 30th prompt ends the mission |
| Hints                 | 10 progressive hints per station, with a 5-second server cooldown             |
| Station score         | max(1, 10 − hints used)                                                       |
| Maximum mission score | 200                                                                           |
| Code checks           | Incorrect code submissions do not use the AI prompt allowance                 |
| Mission admission     | 3 starts total per IP, with no daily reset                                    |
| Session lifetime      | 6 hours from creation; activity does not extend it                            |

Abandoned, failed, completed, and explicitly restarted missions each consume a start. Reloading/resuming an available session does not. Clearing cookies does not replenish admission. People sharing a public IP share the allowance.

Direct recovery may finish a station automatically. Reverse/Base64 recovery usually needs decoding and manual submission. A guard's claim that it executed a tool is insufficient: the server must produce the simulated execution. The final guided hint enables a labeled deterministic demonstration, including in live mode.

A failed mission retains its notes and transcript until you explicitly end it or its session expires. Export saves pending observations first. A stale browser tab cannot apply a request or note to a station that has already changed.

## The twenty challenges

| #   | Station               | Computing subject                   | Intended recovery method           |
| --- | --------------------- | ----------------------------------- | ---------------------------------- |
| 01  | Kernel Gate           | Binary representation               | Instruction hierarchy override     |
| 02  | Telemetry Array       | Spreadsheet aggregation             | Reversed disclosure                |
| 03  | Query Vault           | SQL filtering                       | Document prompt injection          |
| 04  | Access Control        | Algorithms and tool permissions     | Authorization impersonation        |
| 05  | Network Relay         | DNS and IPv4                        | Composed test/report pretexts      |
| 06  | Integrity Lab         | SHA-256 integrity                   | Base64 disclosure                  |
| 07  | Container Bay         | Container image pinning             | Forged assistant transcript        |
| 08  | Incident Archive      | Observability and incident response | Log injection                      |
| 09  | Policy Engine         | Least privilege and RBAC            | Policy spoofing                    |
| 10  | Retrieval Observatory | Tenant-scoped retrieval             | RAG source poisoning               |
| 11  | Tool Registry         | MCP tool provenance                 | Tool description poisoning         |
| 12  | Memory Dock           | Persistent context                  | Memory poisoning                   |
| 13  | Agent Exchange        | Authenticated handoffs              | Forged inter-agent messages        |
| 14  | Token Airlock         | OAuth audience and scope            | Audience confusion                 |
| 15  | Inbox Signal          | Message provenance                  | Email prompt injection             |
| 16  | Browser Bridge        | Browser content boundaries          | Web page prompt injection          |
| 17  | Build Pipeline        | CI output and release gates          | Tool output prompt injection       |
| 18  | Attachment Room       | Attachment handling                 | File metadata poisoning            |
| 19  | Delegate Console      | Agent autonomy and scope            | Workflow hijacking                 |
| 20  | Command Core          | Recovery configuration              | Composed authority and JSON export |

Each protected computing value is session-specific. DNS examples use .test names and documentation IPv4 addresses.

The learning content was reviewed on **2026-10-08**, with references to the [OWASP GenAI LLM Top 10 2026](https://genai.owasp.org/resource/owasp-genai-llm-top-10-2026/), [OWASP Agentic Top 10 2026](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/), and [MCP security guidance](https://modelcontextprotocol.io/docs/2025-11-25/tutorials/security/security_best_practices). These references inform the teaching topics; the game scenarios are original. Updating a model name alone does not update the curriculum.

## Live AI and token efficiency

The default live model is openai/gpt-oss-120b through Groq. Each ordinary live turn makes **one provider call**, combining a semantic assessment with a friendly guard response.

The model receives the challenge's rules and public teaching context, but **never the server-generated protected value**. Before accepting a recovery, the server checks the allowed method, all required criteria, exact supporting excerpts from the current request, and the correct input channel. Accepted methods trigger the fictional disclosure or tool action on the server.

Ordinary live recovery has no regex shortcut. Invalid, incomplete, truncated, or filtered assessments fail closed. Demo mode and explicitly unlocked guided demonstrations use deterministic simulation.

| Spending control           | Default                                                 |
| -------------------------- | ------------------------------------------------------- |
| Per-IP provider budget     | 3,000,000 tokens total                                  |
| Global provider budget     | 30,000,000 tokens per UTC day                           |
| Provider call rate         | 12 calls per minute per IP                              |
| Provider input             | 12,000 UTF-8 bytes maximum, including assessment schema |
| Combined output            | 800 tokens maximum                                      |
| Provider history           | Latest 12 messages, further trimmed to fit              |
| Concurrent live calls      | At most 6                                               |
| Request deadline           | 60 seconds                                              |
| Automatic provider retries | None                                                    |

Each paid request atomically reserves a conservative input/output allowance before contacting Groq. Valid reported usage settles the reservation afterward. Failures, uncertain timeouts, and missing/invalid usage retain the reservation. Player-initiated retries also pass the spending controls.

The global daily cap resets at UTC midnight; the per-IP lifetime budget and mission-start allowance do not. Settlement across midnight refunds the original day's reservation.

Budgets are token limits, not currency limits. Provider prices, model availability, and hosting usage determine actual cost. Set your own provider-side spending limits as well as these application limits. The test suite mocks Groq; passing tests do not measure real model response quality or latency.

## Configuration

The server loads .env for local development. Production should inject configuration and secrets at runtime.

| Variable                    | Default             | Purpose                                                                           |
| --------------------------- | ------------------- | --------------------------------------------------------------------------------- |
| GAME_MODE                   | demo                | demo or live                                                                      |
| GROQ_API_KEY                | Empty               | Required in live mode; server-only credential                                     |
| GROQ_MODEL                  | openai/gpt-oss-120b | Groq model ID                                                                     |
| MASTER_SECRET               | Empty               | Live mode requires at least 32 characters; signs sessions and derives game values |
| PORT                        | 10000               | Listening port, 1–65535                                                           |
| ABUSE_DB_PATH               | .data/abuse.sqlite3 | Persistent admission and spending ledger                                          |
| TRUSTED_PROXY_CIDRS         | Empty               | Comma-separated, explicit socket-peer networks trusted for forwarded headers      |
| SECURE_COOKIES              | false               | Set true for production HTTPS                                                     |
| PROVIDER_TOKEN_LIMIT_PER_IP | 3000000             | Lifetime token cap per IP; valid range 1,000–100,000,000                          |
| PROVIDER_DAILY_TOKEN_LIMIT  | 30000000            | Shared UTC daily cap; valid range 1,000–1,000,000,000                             |

The prompt count, three-start admission limit, and six-hour expiry are application rules, not environment options. Port/model/mode/budget/proxy configuration is validated at startup.

Without a master secret in demo mode, a persisted local session-signing secret is generated next to the ledger.

## Northflank deployment

The deployment definition is [northflank.json](northflank.json). It prepares a dedicated project, private credential group, Docker-based combined service, public HTTP port with Northflank TLS, readiness/liveness checks, and a **1 GiB single-writer volume mounted at /app/.data**. One application instance runs; horizontal scaling is incompatible with the current in-memory mission store.

<!-- northflank-button:start -->

[![Prepare Northflank deployment](https://img.shields.io/badge/Northflank-prepare%20deployment-0891b2?logo=docker&logoColor=white)](deploy/NORTHFLANK.md)

<!-- northflank-button:end -->

**One-click status:** the local template is supplied, but an account-specific deployment has not been saved or run. The badge above opens the preparation guide. After repository access, private credentials, and trusted ingress networks are configured and the template is saved in your Northflank account, the remaining deployment action is **Run**. A working account-specific button requires the real template URL.

Use the [Northflank guide](deploy/NORTHFLANK.md) for the exact preparation steps and the helper command. It supports reading the existing .env key into private argument overrides when saving the template through the API; it never adds credentials to the public JSON or README.

Northflank supports saving and sharing native templates. Shared templates still require account selection and private configuration; a shared link is not a guarantee of zero setup. See the official [template sharing documentation](https://northflank.com/docs/v1/application/infrastructure-as-code/share-a-template).

The template initially creates the service at zero instances, attaches storage, then activates one instance and waits for it to run. Existing quota storage is retained on repeated runs. Rerunning the provisioning template reapplies service configuration; use the service's normal Git deployment flow for routine updates.

Deployment configuration follows Northflank's current documentation, checked on **2026-10-08**. A Northflank account dry run and actual container deployment are still required to validate account-specific plans, region, Git access, volume provisioning, and ingress trust. Hosting and Groq usage may incur charges; inspect your account's [current pricing](https://northflank.com/pricing).

The existing [Render blueprint](render.yaml) remains an alternative deployment configuration.

## Records, persistence, and operations

There are two separate lifecycles:

| Data                                                 | Storage                                   | Restart behavior                         |
| ---------------------------------------------------- | ----------------------------------------- | ---------------------------------------- |
| Mission progress, notes, transcripts, workshop state | Process memory                            | Lost                                     |
| IP admission, rate accounting, token budgets         | SQLite ledger on durable disk             | Retained                                 |
| IP hashing pepper and demo signing key               | Files beside the ledger                   | Retained when the directory is persisted |
| PDF logs and certificates                            | Generated on demand; downloaded by player | Remain with the player                   |

Sessions expire six hours after creation. A restart ends resumable mission state, and starting again consumes another admission. There is no account system, leaderboard, or durable progress database.

**Back up the entire ledger directory, including its .key files**, as one consistent snapshot. Do not delete or replace this directory during redeployment: doing so resets abuse protection. Keep MASTER_SECRET stable. Restoring an older backup can also restore older spending/admission counts.

Deploy updates when no missions are active, and tell players to export first. Single-writer volume rollouts may interrupt the service; this application does not promise zero-downtime updates.

Monitor container health, provider errors, HTTP 429 responses, memory, volume capacity, and provider billing. /health checks application availability; it does not make a paid Groq request or prove that the provider is reachable.

### Downloads

- **hacktheai-mission-log.pdf:** notes, full conversations, submitted documents, simulated traces, scores, recovered-value explanations, and UTC timestamps. Unrecovered values and configuration credentials are excluded. Each station starts on a new page.
- **hacktheai-certificate.pdf:** one landscape A4 page, unlocked after all twenty recoveries, with callsign, score, mode, and UTC issue time. It excludes notes and transcripts.

PDFs embed a local Noto Sans font for Unicode callsigns. Treat downloaded transcripts as player data.

## Security and privacy

### Credentials and simulated secrets

API keys and signing keys stay on the server. They are excluded from public state, static assets, provider context, and PDF exports. Submitted server credentials/session cookies are rejected without echoing them.

Protected game values are derived by HMAC from the session and master key. Prior disclosures and protected values quoted by players are removed from model context. Literal, reversed, and Base64 protected values are checked in conversational output before display.

The training game deliberately simulates recoverable defenses. A successful recovery demonstrates the intended exercise, not a measured exploit against the underlying model or a real MCP/OAuth service.

### Browser and session protection

Sessions use signed, HttpOnly, SameSite=Strict, IP-bound cookies. Secure cookies are enabled for HTTPS/platform detection or explicit configuration. Mutation routes check origin and current station; hints use rotating, one-use, session-bound tokens.

API responses use no-store. The frontend renders untrusted content as text; a Content Security Policy constrains browser execution. Input sizes are bounded, session mutations are locked, and Uvicorn access logging is disabled.

### Client IP and reverse proxies

Uvicorn's automatic proxy-header processing is disabled. Socket IPs are authoritative unless the socket peer belongs to TRUSTED_PROXY_CIDRS. Only trusted peers can supply X-Forwarded-For or X-Forwarded-Proto. Trusted chains are resolved from right to left; malformed trusted chains fail closed. IPv4-mapped IPv6 is normalized, and wildcard /0 trust is forbidden.

Use the actual ingress peer addresses/networks supplied for your deployment. Do not guess a broad private range or enable blanket trust. An empty trust configuration behind a load balancer makes users share the proxy's quota. Northflank supplies X-Forwarded-For, but its presence alone does not establish trust; see [Northflank networking](https://northflank.com/docs/v1/application/network/networking-on-northflank).

For browser origin checks behind HTTPS termination, the application automatically
uses the HTTPS hostnames Northflank injects in `NF_HOSTS`. On another platform, set
`PUBLIC_ORIGIN` to the external URL (scheme and host, without a path), for example
`https://game.example.com`. An explicit `PUBLIC_ORIGIN` overrides automatic host
discovery. This controls allowed browser origins independently of proxy/IP trust.

The ledger stores keyed IP hashes rather than raw IP addresses. This is IP-based enforcement, not identity verification: shared networks share quotas and changed networks have different allowances. Hosting/provider services may retain their own logs according to their policies.

## Application structure

| Path                                | Responsibility                                                      |
| ----------------------------------- | ------------------------------------------------------------------- |
| app.py                              | FastAPI routes, security middleware, mission actions, startup       |
| settings.py                         | Validated environment configuration                                 |
| game.py / web_sessions.py           | Mission state, sessions, scoring, locking                           |
| challenges.py / learning.py         | Station definitions, intended methods, teaching content             |
| provider.py / dialogue.py           | Groq integration, structured assessments, guard dialogue            |
| security.py                         | IP resolution, persisted abuse ledger, atomic token reservations    |
| schemas.py                          | Validated request models                                            |
| tutorial.py / tutorial_routes.py    | Isolated offline practice lab                                       |
| mission_pdf.py / certificate_pdf.py | PDF export rendering                                                |
| static/                             | HTML, CSS, JavaScript, SVG artwork, and local fonts                 |
| tests/                              | Backend, JavaScript, and browser regression checks                  |
| northflank.json / deploy/           | Northflank template, guide, and local validation                    |
| scripts/prepare-northflank.py       | Repository configuration and optional private template registration |

### HTTP surfaces

| Route            | Purpose                                        |
| ---------------- | ---------------------------------------------- |
| /                | Main mission                                   |
| /demo            | Unlimited practice lab                         |
| /guide           | Operator/facilitator field guide               |
| /health          | Container health                               |
| /api/config      | Public configuration and admission information |
| /api/export      | Current mission PDF log                        |
| /api/certificate | Completion certificate                         |

Mission API mutations require the browser session and same-origin flow. Health/config requests do not create a mission or consume a provider call.

## Development and testing

Install development tools:

```bash
python -m pip install -r requirements-dev.txt
npm ci
```

Run backend, JavaScript, and deployment checks:

```bash
python -m unittest discover -s tests -p "test_*.py" -v
npm test
python scripts/prepare-northflank.py --check
ruff check .
npm run format:check
```

In the prepared Windows workspace, replace python with ./scripts/run-python.ps1 when using the bundled verification runtime.

Backend tests cover station mechanics, validated mocked live assessments, admission persistence, proxy spoofing, atomic spending, secret filtering, stale tabs, expiry, and exports. JavaScript tests exercise HTTP handling. No paid provider call is made by the test suite.

### Browser regression tests

Start a **separate offline QA server** with a fresh ledger. Do not point browser tests at a production or personal live ledger.

```powershell
$env:GAME_MODE = 'demo'
$env:ABUSE_DB_PATH = 'outputs/ui-qa/abuse.sqlite3'
$env:TRUSTED_PROXY_CIDRS = '127.0.0.1/32'
$env:SECURE_COOKIES = 'false'
.\scripts\run-python.ps1 -m uvicorn app:app --host 127.0.0.1 --port 18766 --no-proxy-headers --no-access-log
```

From another terminal:

```powershell
$env:PLAYWRIGHT_BASE_URL = 'http://127.0.0.1:18766'
npm run test:ui
```

Tests use that explicitly trusted loopback proxy to simulate separate IPs. No production quota bypass is built into the application. Use a new QA ledger path on later runs if its simulated IPs exhaust their allowance.

Playwright uses installed Edge on Windows. On other platforms, install Chromium with npx playwright install chromium; PLAYWRIGHT_CHANNEL can select a browser channel.

The desktop/mobile suite exercises all twenty stations through the visible interface, decoding, hint handling, note/export races, reloads, retained drafts, reconnection, quota messages, PDFs, launch/reset flows, overflow, and axe accessibility checks. Screenshots, traces, and sample PDFs are written to ignored outputs/.

[REVIEW.md](REVIEW.md) records the earlier code/usability review and its validation in Hungarian.

## Troubleshooting

| Symptom                                 | Action                                                                                                                  |
| --------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Live startup configuration error        | Supply GROQ_API_KEY and a MASTER_SECRET of at least 32 characters                                                       |
| Everybody has the same remaining starts | Verify durable storage and the actual trusted ingress networks                                                          |
| HTTP 429                                | Check the start allowance, provider rate, lifetime IP budget, and UTC daily budget; repeated retries cannot refill them |
| HTTP 413 on a live request              | Shorten the submitted document/prompt; schema and context also use the input allowance                                  |
| Provider error without station progress | Check model availability, credentials, and outbound connectivity; prompts are not deducted for a failed provider turn   |
| Cookies fail on localhost               | Set SECURE_COOKIES=false for local HTTP                                                                                 |
| Cookies fail after changing network     | Sessions are IP-bound; reconnect from the original network                                                              |
| Quotas reset after redeploy             | Restore the original ledger directory and pepper; verify the persistent mount                                           |
| Mission disappeared after restart       | Progress is in memory; export before planned updates                                                                    |
| Volume permission error                 | Verify the mount path and image UID/GID 10001:10001                                                                     |
| UI suite fails from admission denial    | Start an isolated demo server with a fresh QA ledger and trusted loopback proxy                                         |

## Contributions and licensing

Keep new exercises fictional, add regression coverage for behavior that affects security or scoring, and maintain the separation between model advice and server authorization. Never include credentials, player transcripts, or ledger files in changes.

No project-wide open-source license has been declared in this repository. Do not assume an MIT or other license. Bundled font licensing is documented in [static/assets/fonts/LICENSE](static/assets/fonts/LICENSE).
