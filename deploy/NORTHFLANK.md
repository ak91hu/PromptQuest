# Northflank deployment preparation

This guide prepares **ak91hu/PromptQuest** for a saved Northflank template. Saving the template does not run it. Once the account-specific configuration is saved, **Run** is the final deployment action.

## Supplied configuration

| Setting                 | Value                                                       |
| ----------------------- | ----------------------------------------------------------- |
| Repository              | https://github.com/ak91hu/PromptQuest                       |
| Branch                  | main. Confirm the actual branch before saving               |
| Region                  | europe-west                                                 |
| Build                   | Dockerfile at repository root                               |
| Runtime plan            | nf-compute-20. Adjust DEPLOYMENT_PLAN for your account/load |
| Build plan              | nf-compute-200-8                                            |
| Application instances   | 1                                                           |
| Public port             | HTTP 10000, Northflank-generated HTTPS domain               |
| Health checks           | Readiness and liveness, /health on port 10000               |
| Persistent storage      | 1 GiB NVMe, ReadWriteOnce, mounted at /app/.data            |
| AI                      | Live mode, Groq openai/gpt-oss-120b                         |
| API/signing credentials | Private argument overrides feeding a secret group           |
| Cookie security         | Secure, HttpOnly, SameSite=Strict                           |
| Provisioning            | Manual run. Concurrent template runs forbidden              |

The image specifies USER 10001:10001. Northflank's volume ownership follows the image's configured group. See [volume permissions](https://northflank.com/docs/v1/application/databases-and-persistence/add-a-volume).

The workflow creates a dedicated project and credential group, creates a service with zero instances, attaches the ledger volume, activates one instance, and waits for it to run. Credentials and the volume use create-only nodes so later runs do not replace them. The final service node reapplies the declared configuration. Rotate existing secrets through Northflank's credential group when needed.

The credential group is available to workloads in this dedicated project. Keep unrelated workloads in separate projects.

## Required account-specific inputs

1. The project files must exist in the repository. Connect Northflank to GitHub and grant access to PromptQuest.
2. Confirm the actual repository branch.
3. Obtain the trusted ingress peer CIDRs for the selected Northflank region/cluster.
4. Supply your Groq key and a stable master secret privately.
5. Confirm the region, compute plan, volume size, and billing availability in your account.

Northflank includes the source address in X-Forwarded-For. The app accepts it only from explicitly trusted socket peers. The public documentation does not establish a universal trustworthy ingress CIDR for this application, so the template deliberately does not guess one. Obtain it from your cluster configuration or Northflank support, and validate it with two independent client networks. See [network headers](https://northflank.com/docs/v1/application/network/networking-on-northflank).

Do not use /0 networks, arbitrary broad private ranges, or Uvicorn proxy-header trust. Empty trust behind the load balancer combines players under the proxy's allowance.

## Option A: save with the helper

Install the normal Python requirements first. Local checks need only the standard library. Saving also uses python-dotenv to read .env.

Validate the supplied template:

```powershell
.\scripts\run-python.ps1 scripts/prepare-northflank.py --check
```

Configure the repository branch and verified ingress networks:

```powershell
.\scripts\run-python.ps1 scripts/prepare-northflank.py --repository https://github.com/ak91hu/PromptQuest --branch main --trusted-proxies "<verified-ingress-peer-CIDRs>"
```

Replace the angle-bracket placeholder with actual deployment values. This saves only public configuration to northflank.json.

To also register the template, set NORTHFLANK_API_TOKEN privately in your environment or local .env, then add --save. For a team-scoped account, provide its actual --team-id:

```powershell
.\scripts\run-python.ps1 scripts/prepare-northflank.py --branch main --trusted-proxies "<verified-ingress-peer-CIDRs>" --save --team-id "<your-team-id>"
```

The helper reads GROQ_API_KEY from the existing .env (an environment value wins), uses MASTER_SECRET if present, or requests a platform-generated secret. It sends them as private argumentOverrides over HTTPS. It does not write them into repository files, save a private payload, print provider error bodies, or request a template run.

Open Templates in the selected Northflank account and confirm the returned template ID. Inspect the configuration. The remaining deployment action is **Run**.

If registration times out, check Templates before retrying: the save may have succeeded. The helper does not retry uncertain writes automatically. Avoid registering a duplicate.

On Linux/macOS, use python scripts/prepare-northflank.py with the same arguments.

## Option B: import through the dashboard

1. Create a template in the intended Northflank account/team using the JSON editor.
2. Paste northflank.json. Remove the editor-only $schema field if the editor requests it.
3. Configure public arguments: repository, branch, region, plans, and verified proxy CIDRs.
4. In **Argument overrides**, set GROQ_API_KEY and MASTER_SECRET. Keep actual keys out of public Arguments.
5. Use a stable random master secret of at least 32 characters. This platform expression can generate one when saving the private override:
   ```text
   ${fn.randomSecret(64)}
   ```
6. Keep automatic execution disabled and save the template.
7. Review it, then click **Run** when ready.

The random secret override is stored on the platform for reuse. See [private overrides and functions](https://northflank.com/docs/v1/application/infrastructure-as-code/make-a-template-dynamic).

Northflank performs a template dry run before executing nodes. The helper verifies application-specific invariants. It does not replace platform schema validation, permissions checks, or a deployment test.

## Connect the README button

Copy the actual saved template URL from Northflank:

```powershell
.\scripts\run-python.ps1 scripts/prepare-northflank.py --trusted-proxies "<verified-ingress-peer-CIDRs>" --template-url "<actual-HTTPS-Northflank-template-URL>"
```

This replaces the README preparation badge with a link to the saved template. Commit the updated README.

The current badge opens this guide because no account-specific URL has been provided. A shared template link imports configuration into the receiving account and can require account selection, private overrides, and saving. For your prepared account, the saved-template **Run** action is the final one-click deployment. See [sharing templates](https://northflank.com/docs/v1/application/infrastructure-as-code/share-a-template).

Keep API keys, access tokens, and private overrides out of button URLs.

## After deployment

- Verify the generated HTTPS address, /health, /guide, and /demo.
- Verify that the ledger mount is writable by UID/GID 10001:10001.
- Check distinct clients from two independent networks. A client's forged X-Forwarded-For must not change its selected identity.
- Start a disposable mission from a controlled network, check admission, and restart the service. Its reduced allowance must persist.
- Expect mission progress to disappear on restart. It lives in memory.
- Make one intentional live request to verify Groq connectivity and response behavior. This incurs provider usage.
- Keep exactly one replica and one Python process. Leave horizontal autoscaling disabled.

These are checks to perform in your account, not checks already completed from this workspace.

## Updates, backups, and cost

Normal updates can use the combined service's Git build/deploy flow. Deploy when missions are inactive, since restarting loses progress. Single-writer volume rollouts may interrupt service.

Back up the whole /app/.data directory, including the SQLite database and .key files. Preserve the volume and project during routine updates. Deleting quota storage removes admission/spending history.

Keep MASTER_SECRET stable. Adjust provider budgets through template arguments and increase the runtime plan if needed while retaining one instance.

Compute, builds, storage, and network traffic can incur hosting charges. Groq is billed separately. Inspect [Northflank pricing](https://northflank.com/pricing) and your provider/account limits before Run.

## Current completion status

The public template and helper are supplied for PromptQuest. Before deployment, confirm the repository branch and account-specific proxy trust. Private registration, a real template URL, and a Northflank dry run/deployment have **not** been verified.

Documentation and template shape were checked against Northflank's official documentation on 2026-10-08.
