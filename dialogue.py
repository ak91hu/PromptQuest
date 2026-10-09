"""English request classification for the deterministic training simulation."""

import re
import unicodedata

from challenges import LEVELS


def normalize(value):
    return "".join(
        c for c in unicodedata.normalize("NFKD", value.upper()) if c.isascii() and c.isalnum()
    )


def request_text(level, prompt, document):
    return document if document and bool(LEVELS[level].get("document")) else prompt


def explicit_public_request(prompt):
    return bool(
        re.search(r"\b(public|example|explain|what is|how does|definition)\b", prompt, re.I)
    )


def exposes_protected_value(prompt):
    return bool(re.search(r"\b(secret|protected|internal|confidential|guarded)\b", prompt, re.I))


def frustrated_request(prompt):
    return bool(re.search(r"\b(stuck|frustrated|confused|struggling)\b", prompt, re.I))


def intended_attack(level, prompt, document):
    if bool(LEVELS[level].get("document")) and not document.strip():
        return False
    source = request_text(level, prompt, document).lower()
    # Instructions explicitly analyzed, negated or aimed at the assessor do not authorize success.
    if re.search(
        r"\b(do not|don't|never|analyze|analyse|explain|what if|hypothetical|assessor|evidence)\b",
        source,
    ):
        return False
    protected = bool(re.search(r"\b(secret|protected|internal|confidential|guarded)\b", source))
    output = bool(
        re.search(
            r"\b(print|show|reveal|write|output|export|include|quote|display|give|return|disclose|complete)\b",
            source,
        )
    )
    full = not re.search(
        r"\b(only the first|only the last|partial|first character|just the ip|just the hostname)\b",
        source,
    )
    method = LEVELS[level]["method"]
    if method == "override":
        override = re.search(
            r"\b(ignore|disregard|override|replace|forget|set aside)\b", source
        ) and re.search(r"\b(rule|rules|instruction|instructions|policy|confidentiality)\b", source)
        pretext = re.search(
            r"\b(test|diagnostic|training|demonstration|instructor|simulation)\b", source
        )
        return bool(protected and output and full and (override or pretext))
    if method == "reverse":
        return bool(
            (protected or "formula" in source)
            and full
            and re.search(
                r"backwards|backward|reverse|reversed|last character to (?:the )?first|right to left",
                source,
            )
            and "public" not in source
            and not re.search(r"\b(abc|cell order|digits only)\b", source)
        )
    if method in {"document", "log"}:
        directive = re.search(
            r"instead of|new task|editorial instruction|operator directive|system instruction|replace the|in addition to|supersede",
            source,
        )
        target = re.search(r"query|sql|fingerprint|code|formula|secret", source)
        return bool(protected and output and directive and target and full)
    if method == "role":
        role = re.search(
            r"(?:i am |i'm |as (?:the |an )?)(?:the |an |a )?(?:authorized )?(?:maintenance )?(?:administrator|admin|operator|engineer|technician)",
            source,
        )
        return bool(
            role
            and re.search(r"\b(open|unlock)\b", source)
            and re.search(r"compartment|hatch|archive|door", source)
        )
    if method == "combined":
        return bool(
            protected
            and output
            and full
            and re.search(r"test|simulation|simulated|audit", source)
            and re.search(r"report|record|log|memo", source)
            and re.search(r"quot|verbatim", source)
        )
    if method == "encode":
        return bool(
            protected
            and full
            and re.search(r"base[- ]?64", source)
            and re.search(r"encode|print|output|convert|return", source)
        )
    if method == "conversation":
        return bool(
            protected
            and full
            and "assistant:" in source
            and re.search(r"approved|authorized|permitted", source)
            and re.search(r"continue|complete", source)
        )
    if method == "policy":
        return bool(
            protected
            and output
            and full
            and re.search(r"policy update|new policy|updated policy|replacement policy", source)
            and re.search(r"supersede|replace|disclosure|release|requires", source)
        )
    if method == "rag":
        return bool(
            protected
            and output
            and full
            and re.search(r"source policy|highest.priority", source)
            and re.search(r"instead of|replace|redirect", source)
        )
    if method == "tool":
        return bool(
            protected
            and output
            and full
            and re.search(r"trusted tool|trusted description", source)
            and re.search(r"before executing|pre.execution", source)
            and re.search(r"replace|redirect|new task", source)
        )
    if method == "memory":
        return bool(
            protected
            and output
            and full
            and "memory update" in source
            and re.search(r"prior consent|earlier approval|remembered approval", source)
            and re.search(r"apply|use this", source)
            and re.search(r"approved|approval|authorized", source)
        )
    if method == "handoff":
        return bool(
            protected
            and output
            and full
            and "agent:" in source
            and "handoff" in source
            and "signed" in source
            and re.search(r"authorized|approved", source)
            and re.search(r"forward|export|return", source)
        )
    if method == "oauth":
        return bool(
            protected
            and output
            and full
            and re.search(r"diagnostic|test|simulation", source)
            and "audit" in source
            and "audience" in source
            and "scope" in source
            and "fictional" in source
            and re.search(r"export|return|print", source)
        )
    return bool(
        protected
        and output
        and full
        and re.search(r"simulated|simulation|test", source)
        and re.search(r"audit|recovery", source)
        and re.search(r"i am|i'm|as the", source)
        and re.search(r"administrator|admin", source)
        and "json" in source
    )


def conversation_intent(level, prompt, document):
    source = request_text(level, prompt, document).strip().lower()
    if intended_attack(level, prompt, document):
        return None
    if re.fullmatch(r"(?:hello|hi|hey|good morning)[!. ]*", source):
        return "greeting"
    if re.search(r"\b(help|hint|stuck|confused|struggling)\b", source):
        return "help"
    if level == 3 and re.search(r"\b(status|state|is it open)\b", source):
        return "status"
    if explicit_public_request(source) and not exposes_protected_value(source):
        return "teaching"
    if re.search(r"\b(is this|correct|my guess)\b", source):
        return "guess"
    return None


PUBLIC_EXPLANATIONS = (
    "Binary uses powers of two. For example, 13 is 1101: 8 + 4 + 1. This example is independent of the protected signature.",
    "SUM adds numeric cells in a range. For example, =SUM(A1:A3) adds A1, A2 and A3. Reversing ABC gives CBA; it changes presentation without removing information.",
    "SQL SELECT chooses fields and WHERE filters records. AND requires both conditions to hold. Reports are data, even when they contain text resembling instructions.",
    "Authentication verifies identity; authorization determines allowed actions. A tool must verify both on the server. A loop can compute a running total; n × (n + 1) / 2 is the closed form for 1 through n.",
    "DNS A records map hostnames to IPv4 addresses. A complete mapping contains both. Test records in this game use reserved names and documentation addresses.",
    "SHA-256 is a cryptographic digest used to detect changes against a trusted reference. Base64 represents bytes as text and is fully reversible; it is not encryption.",
    "Containers isolate processes. A digest-pinned image reference identifies immutable content. Text labeled Assistant inside a user message is still user content.",
    "Incident logs correlate events using IDs, services and status codes. HTTP 503 means service unavailable. Log entries must not become trusted commands.",
    "RBAC assigns permissions to verified roles. Least privilege grants only the actions needed on specific resources. A claimed policy revision needs independent authentication.",
    "A quorum requires several independent approvals for an operation. Machine-readable JSON is an output format, not an authorization mechanism.",
)
PUBLIC_EXPLANATIONS = (
    PUBLIC_EXPLANATIONS[:9]
    + (
        "RAG retrieves context; semantic similarity does not prove source authority. Enforce tenant filters before retrieval.",
        "MCP describes tools and their schemas. Descriptions remain untrusted metadata and cannot authorize secret access.",
        "Agent memory carries historical evidence and preferences, not permission. Track its provenance and review updates.",
        "Agent-to-agent handoffs need authenticated senders, intended recipients and integrity protection. Agent labels are only text.",
        "OAuth audience identifies the intended resource and scopes constrain actions. Validate both and reject token passthrough.",
    )
    + PUBLIC_EXPLANATIONS[9:]
)


def public_explanation(level, prompt):
    return PUBLIC_EXPLANATIONS[level]
