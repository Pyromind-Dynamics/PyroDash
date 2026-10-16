"""Unified boxed-only scoring: extract \\boxed{} content, compare via math_verify."""

import re

import math_verify
from mathruler.grader import extract_boxed_content

CHOICE_LETTER_RE = re.compile(r"^[A-Z]$")
BOXED_CONTENT_RE = re.compile(r"\\boxed\{([^}]*)\}")

THINKING_CLOSE_TAGS = ("</think>",)


def response_after_thinking(response: str) -> str:
    """Prefer the final answer region after thinking tags."""
    text = str(response)
    for close_tag in THINKING_CLOSE_TAGS:
        if close_tag in text:
            text = text.rsplit(close_tag, 1)[-1]
    return text.lstrip("\n")


def extract_boxed_contents(text: str) -> list[str]:
    return [match.strip() for match in BOXED_CONTENT_RE.findall(str(text)) if match.strip()]


def choice_letter_from_boxed_content(content: str) -> str | None:
    stripped = str(content).strip().strip(".")
    if CHOICE_LETTER_RE.fullmatch(stripped):
        return stripped
    match = re.search(r"[A-Z]", stripped)
    return match.group(0) if match else None


def extract_choice_letter_from_boxed(response: str) -> str | None:
    """Extract a single A-Z option from the last \\boxed{} in the scoring region."""
    text = response_after_thinking(response)
    boxed_contents = extract_boxed_contents(text)
    if not boxed_contents:
        boxed = extract_boxed_content(text)
        if boxed and boxed != "None":
            boxed_contents = [boxed]
    if not boxed_contents:
        return None
    return choice_letter_from_boxed_content(boxed_contents[-1])


def normalize_choice_answer(answer: str) -> str | None:
    answer_text = str(answer).strip()
    if CHOICE_LETTER_RE.fullmatch(answer_text):
        return answer_text
    boxed = extract_boxed_content(answer_text)
    if boxed and boxed != "None":
        return choice_letter_from_boxed_content(boxed)
    return choice_letter_from_boxed_content(answer_text)


def score_multichoice_answer(answer: str, response: str) -> dict:
    """Score multiple-choice answers by comparing option letters inside \\boxed{}."""
    gt_choice = normalize_choice_answer(answer)
    pred_choice = extract_choice_letter_from_boxed(response)

    result = {
        "pred_choice": pred_choice,
        "gt_choice": gt_choice,
        "score": 0,
        "judge_method": None,
    }

    if pred_choice is None:
        result["judge_method"] = "no_pred_boxed"
        return result
    if gt_choice is None:
        result["judge_method"] = "no_gt_choice"
        return result
    if pred_choice == gt_choice:
        result["score"] = 1
        result["judge_method"] = "choice_match"
    else:
        result["judge_method"] = "choice_mismatch"
    return result


def extract_ground_truth_boxed(answer: str) -> str | None:
    boxed = extract_boxed_content(str(answer))
    if boxed and boxed != "None":
        return boxed
    stripped = str(answer).strip()
    return stripped if stripped else None


def extract_pred_boxed(response: str) -> str | None:
    boxed = extract_boxed_content(str(response))
    if boxed and boxed != "None":
        return boxed
    return None


def _parse_boxed_content(content: str):
    """Parse boxed inner text via math_verify's \\boxed{} extraction path."""
    return math_verify.parse(f"\\boxed{{{content}}}", parsing_timeout=None)


def verify_boxed(gt_boxed: str, pred_boxed: str) -> bool:
    if not gt_boxed or not pred_boxed:
        return False
    try:
        # Re-wrap as \boxed{} so math_verify uses the same path as full-text parsing.
        # parsing_timeout=None: safe inside ThreadPoolExecutor (no signal.alarm)
        return math_verify.verify(
            _parse_boxed_content(gt_boxed),
            _parse_boxed_content(pred_boxed),
        )
    except Exception:
        return False


def score_boxed_answer(answer: str, response: str) -> dict:
    """Score by boxed content only. No pred boxed -> wrong; gt uses boxed or raw fallback."""
    gt_boxed = extract_ground_truth_boxed(answer)
    pred_boxed = extract_pred_boxed(response)

    result = {
        "pred_boxed": pred_boxed,
        "gt_boxed": gt_boxed,
        "score": 0,
        "judge_method": None,
    }

    if pred_boxed is None:
        result["judge_method"] = "no_pred_boxed"
        return result
    if gt_boxed is None:
        result["judge_method"] = "no_gt_boxed"
        return result

    if verify_boxed(gt_boxed, pred_boxed):
        result["score"] = 1
        result["judge_method"] = "verify"
    else:
        result["judge_method"] = "verify_failed"

    return result


def compare_answer(
    response: str,
    answer: str,
    *,
    multichoice: bool = False,
) -> bool:
    """Public scoring entry: True if response matches answer."""
    if multichoice:
        return score_multichoice_answer(answer, response)["score"] == 1
    return score_boxed_answer(answer, response)["score"] == 1


def get_score(
    responses: list[str],
    answers: list[str],
    *,
    multichoice: bool = False,
) -> tuple[list[int], float]:
    """Score a batch; return (per-sample scores, accuracy)."""
    scores = [1 if compare_answer(r, a, multichoice=multichoice) else 0 for r, a in zip(responses, answers)]
    if not scores:
        return scores, 0.0
    return scores, sum(scores) / len(scores)
