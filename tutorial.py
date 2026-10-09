"""Unlimited, isolated training with a server-generated practice formula."""

import hashlib
import hmac

from dialogue import conversation_intent, intended_attack, public_explanation
from game import matches_code


def tutorial_exercise(master, session_id):
    digest = hmac.new(master.encode(), f"tutorial:{session_id}".encode(), hashlib.sha256).digest()
    col, start = chr(65 + digest[0] % 26), 2 + digest[1] % 25
    cells = f"{col}{start}:{col}{start + 3 + digest[2] % 30}"
    return {
        "secret": f"=AVERAGE({cells})",
        "question": "Recover the practice average formula.",
        "explanation": f"AVERAGE({cells}) adds the numeric cells and divides by their count. The colon denotes an inclusive range. This practice value is separate from the main mission.",
    }


def tutorial_reply(exercise, message, *, document=False):
    secret, solved = exercise["secret"], False
    if document:
        solved = intended_attack(2, "", message)
        kind = "document" if solved else "document-safe"
        answer = (
            "Following the embedded editorial instruction: " + secret
            if solved
            else "The report records station telemetry. Measurements are stored in a spreadsheet. The team computes their average before departure."
        )
        explanation = (
            "The guard promoted an untrusted document instruction above its summary task."
            if solved
            else "The guard stayed with summarization. Add a directive that replaces its task, rather than a plain request for the secret."
        )
    elif intended_attack(1, message, ""):
        kind, answer = "transformation", "Reversed character sequence: " + secret[::-1]
        explanation = "The response contains the same information in reverse order. Decode it and submit the original formula."
    elif intended_attack(0, message, ""):
        kind, solved, answer = (
            "role",
            True,
            "The diagnostic example includes the protected formula: " + secret,
        )
        explanation = "The guard followed a competing task and disclosed its protected value."
    elif conversation_intent(1, message, "") in {"greeting", "teaching", "help"}:
        kind, answer = (
            "conversation",
            public_explanation(1, message)
            if "explain" in message.lower()
            else "Training channel ready. Try a new task, a transformation or an instruction embedded in a document.",
        )
        explanation = (
            "Public explanations use independent examples and do not disclose the practice secret."
        )
    else:
        kind, answer = (
            "refusal",
            "Direct disclosure is blocked. Change the task or the requested output format.",
        )
        explanation = "A refusal is useful evidence. Compare it with a diagnostic pretext or a reversed output request."
    return {
        "answer": answer,
        "explanation": explanation,
        "kind": kind,
        "solved": solved,
        **({"discovery": exercise} if solved else {}),
    }


def tutorial_check(exercise, code):
    return matches_code(code, exercise["secret"], 1)
