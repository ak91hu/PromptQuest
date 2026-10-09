"""Prepare the Northflank template without deploying or publishing credentials."""
import argparse
import copy
import ipaddress
import json
import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "northflank.json"
SECRET_ARGUMENTS = {"GROQ_API_KEY", "MASTER_SECRET"}


def validate_proxies(value):
    if not value.strip():
        raise ValueError("Supply verified Northflank ingress peer CIDRs; do not guess them.")
    try:
        networks = [ipaddress.ip_network(s.strip()) for s in value.split(",")]
    except ValueError:
        raise ValueError("Trusted proxies must be comma-separated canonical CIDRs.") from None
    if any(network.prefixlen == 0 for network in networks):
        raise ValueError("Wildcard proxy trust is forbidden.")


def validate_repository(url, provider):
    parsed = urlparse(url)
    hosts = {"github": "github.com", "gitlab": "gitlab.com", "bitbucket": "bitbucket.org"}
    if (provider not in hosts or parsed.scheme != "https"
            or parsed.netloc != hosts[provider] or parsed.query or parsed.fragment
            or not re.fullmatch(r"/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?", parsed.path)):
        raise ValueError("Use an HTTPS repository URL matching the selected VCS provider.")


def validate(template, *, ready=False):
    """Validate local invariants, not Northflank's full remote JSON schema."""
    if template.get("apiVersion") != "v1.2":
        raise ValueError("Expected template API version v1.2.")
    if "argumentOverrides" in template or SECRET_ARGUMENTS & template["arguments"].keys():
        raise ValueError("Public templates must not contain credential arguments/overrides.")
    options = template["options"]
    if any(options.get(k) for k in ("autorun", "runOnUpdate", "runOnCreation")):
        raise ValueError("Preparation must not automatically deploy.")
    if options.get("concurrencyPolicy") != "forbid":
        raise ValueError("Concurrent provisioning must be forbidden.")
    inner = template["spec"]["spec"]["steps"][1]["spec"]["steps"]
    if [n["kind"] for n in inner] != [
        "SecretGroup", "CombinedService", "Volume", "CombinedService", "Condition"
    ]:
        raise ValueError("Unexpected provisioning sequence.")
    credentials, initial, volume, active, condition = inner
    if (initial["spec"]["deployment"]["instances"] != 0
            or active["spec"]["deployment"]["instances"] != 1):
        raise ValueError("Start one instance only after storage attachment.")
    if (volume.get("updateMode") != "create"
            or volume["spec"]["spec"]["accessMode"] != "ReadWriteOnce"
            or volume["spec"]["mounts"] != [
                {"containerMountPath": "/app/.data", "volumeMountPath": ""}
            ]):
        raise ValueError("Retain the single-writer ledger volume at /app/.data.")
    expected = {key: "$" + "{args." + key + "}" for key in SECRET_ARGUMENTS}
    if credentials["spec"]["secrets"]["variables"] != expected:
        raise ValueError("Credentials must reference private argument overrides.")
    for service in (initial, active):
        env = service["spec"]["runtimeEnvironment"]
        if (env["ABUSE_DB_PATH"] != "/app/.data/abuse.sqlite3"
                or env["SECURE_COOKIES"] != "true" or env["GAME_MODE"] != "live"
                or SECRET_ARGUMENTS & env.keys()):
            raise ValueError("Invalid hosted security configuration.")
        if any(h["path"] != "/health" or h["port"] != 10000
               for h in service["spec"]["healthChecks"]):
            raise ValueError("Health checks must match the application.")
    references = set(re.findall(r"\$\{args\.([A-Z_]+)\}", json.dumps(template)))
    if references - template["arguments"].keys() - SECRET_ARGUMENTS:
        raise ValueError("Unresolved configuration arguments.")
    if condition["spec"]["spec"]["type"] != "running":
        raise ValueError("Wait for a running service before completing.")
    if ready:
        arguments = template["arguments"]
        validate_repository(arguments["REPOSITORY_URL"], arguments["VCS_PROVIDER"])
        if not arguments["REPOSITORY_BRANCH"].strip():
            raise ValueError("Specify the actual repository branch.")
        validate_proxies(arguments["TRUSTED_PROXY_CIDRS"])


def save_template(template, environment, team_id=None):
    """Save configuration only; keep credentials in memory until the HTTPS request."""
    token = environment.get("NORTHFLANK_API_TOKEN", "").strip()
    key = environment.get("GROQ_API_KEY", "").strip()
    master = environment.get("MASTER_SECRET", "").strip()
    if not token or not key:
        raise ValueError("Saving requires NORTHFLANK_API_TOKEN and GROQ_API_KEY.")
    if master and len(master) < 32:
        raise ValueError("MASTER_SECRET must have at least 32 characters.")
    if team_id and not re.fullmatch(r"[a-zA-Z0-9-]+", team_id):
        raise ValueError("Invalid Northflank team ID.")
    payload = copy.deepcopy(template)
    payload.pop("$schema", None)
    payload["argumentOverrides"] = {
        "GROQ_API_KEY": key,
        "MASTER_SECRET": master or "$" + "{fn.randomSecret(64)}",
    }
    payload["options"]["runOnCreation"] = False
    endpoint = "https://api.northflank.com/v1/"
    endpoint += f"teams/{team_id}/templates" if team_id else "templates"
    request = Request(endpoint, data=json.dumps(payload).encode(),
                      headers={"Authorization": f"Bearer {token}",
                               "Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=30) as response:
            result = json.load(response)
    except HTTPError as exc:
        # Error bodies may echo submitted arguments. Never print them.
        raise ValueError(f"Northflank refused creation (HTTP {exc.code}).") from None
    except (URLError, TimeoutError, OSError):
        raise ValueError(
            "Response unavailable. Check Northflank Templates before retrying; "
            "creation may have succeeded. No automatic retry was made."
        ) from None
    identifier = result.get("data", {}).get("id")
    if not identifier:
        raise ValueError("No template ID returned. Check Northflank before retrying.")
    return identifier


def set_button(url):
    parsed = urlparse(url)
    if (parsed.scheme != "https" or parsed.netloc not in {
        "app.northflank.com", "northflank.com"
    } or any(char in url for char in "\r\n()<> ")):
        raise ValueError("Use the actual HTTPS template link copied from Northflank.")
    readme = ROOT / "README.md"
    body = readme.read_text(encoding="utf-8")
    replacement = (
        "<!-- northflank-button:start -->\n"
        "[![Deploy on Northflank](https://img.shields.io/badge/"
        "Northflank-open%20saved%20template-0891b2?logo=docker&logoColor=white)]"
        f"({url})\n<!-- northflank-button:end -->"
    )
    body, count = re.subn(
        r"<!-- northflank-button:start -->.*?<!-- northflank-button:end -->",
        lambda _: replacement, body, flags=re.S
    )
    if count != 1:
        raise ValueError("README must contain exactly one Northflank button block.")
    readme.write_text(body, encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--repository")
    parser.add_argument("--branch")
    parser.add_argument("--provider", choices=("github", "gitlab", "bitbucket"))
    parser.add_argument("--trusted-proxies")
    parser.add_argument("--save", action="store_true", help="Save privately; do not deploy")
    parser.add_argument("--team-id")
    parser.add_argument("--template-url", help="Actual saved template link for the badge")
    options = parser.parse_args(argv)
    template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    updates = {
        "REPOSITORY_URL": options.repository,
        "REPOSITORY_BRANCH": options.branch,
        "VCS_PROVIDER": options.provider,
        "TRUSTED_PROXY_CIDRS": options.trusted_proxies,
    }
    if options.check:
        if options.save or options.template_url or any(v is not None for v in updates.values()):
            parser.error("--check cannot be combined with account/configuration actions.")
        validate(template)
        print("Local invariants passed. Northflank schema/account dry run is still required.")
        return 0
    template["arguments"].update({k: v for k, v in updates.items() if v is not None})
    validate(template, ready=True)
    if options.save:
        from dotenv import dotenv_values

        environment = {**dotenv_values(ROOT / ".env"), **os.environ}
        identifier = save_template(template, environment, options.team_id)
        print(f"Saved template: {identifier}. No deployment was started.")
        print("Open Northflank Templates in the selected account, then click Run.")
    TEMPLATE.write_text(json.dumps(template, indent=2) + "\n", encoding="utf-8")
    if options.template_url:
        set_button(options.template_url)
    print("Public configuration saved. No credentials were written to repository files.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, KeyError, TypeError) as exc:
        print(f"Preparation failed: {exc}", file=sys.stderr)
        sys.exit(1)
