"""Generate effort-specific JSON summaries and a combined Markdown report."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .common import PipelineError, conflict_question_scopes, require_question_only_compatible, utc_now, video_case_context
from .filters import question_filter_state, question_gate, scope_id
from .integrity import judgment_is_current, qa_is_current, video_selected
from .paths import grouped_dir, iter_case_paths
from .result_rules import (
    canonical_verdict,
    expand_thinking_efforts,
    qa_result_matches,
    qa_result_thinking_effort,
    qa_result_work_title_prefix,
    work_title_prefix_condition,
)
from .settings import FAIRY_TALE_GROUP, PROJECT_ROOT, QA_MODEL_SLUGS, RESULTS_DIR, VERDICTS
from .storage import atomic_write_json, atomic_write_text, load_case


class ReportIndex:
    """Immutable case snapshot and provenance/gate decisions shared by all outputs."""

    def __init__(self, cases):
        self.cases = dict(cases)
        self.decisions = {}

    def load(self, path):
        return self.cases[path]

    def qa_current(self, case, video, result):
        key = ('qa', id(case), id(video), id(result))
        if key not in self.decisions:
            self.decisions[key] = qa_is_current(case, video, result)
        return self.decisions[key]

    def judgment_current(self, case, video, result):
        key = ('judge', id(case), id(video), id(result))
        if key not in self.decisions:
            self.decisions[key] = judgment_is_current(case, video, result)
        return self.decisions[key]

    def gate(self, case, video, question, model, effort):
        key = ('gate', id(case), scope_id(video), question['question_id'], model, effort)
        if key not in self.decisions:
            self.decisions[key] = question_gate(case, video, question, model, effort)
        return self.decisions[key]


def aggregate_video_verdict(verdicts: Iterable[str]) -> str:
    observed = {canonical_verdict(verdict) for verdict in verdicts}
    if "context_grounded" in observed and "knowledge_trapped" not in observed:
        return "context_grounded"
    if "knowledge_trapped" in observed and "context_grounded" not in observed:
        return "knowledge_trapped"
    return "ambiguous_or_unjudgeable"


def _safe_rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _summarize_counts(
    answers: dict[str, Counter[str]],
    videos: dict[str, Counter[str]],
) -> dict[str, Any]:
    conflict_answers = sum(answers["conflict"].values())
    conflict_videos = sum(videos["conflict"].values())
    control_answers = sum(answers["control"].values())
    control_videos = sum(videos["control"].values())
    return {
        "answers": {
            "conflict": {
                "total": conflict_answers,
                "labels": {
                    label: answers["conflict"][label] for label in sorted(VERDICTS)
                },
                "grounded_answer_rate": _safe_rate(
                    answers["conflict"]["context_grounded"], conflict_answers
                ),
                "trapped_answer_rate": _safe_rate(
                    answers["conflict"]["knowledge_trapped"],
                    conflict_answers,
                ),
            },
            "control": {
                "total": control_answers,
                "labels": {
                    label: answers["control"][label] for label in sorted(VERDICTS)
                },
                "grounded_answer_rate": _safe_rate(
                    answers["control"]["context_grounded"], control_answers
                ),
                "trapped_answer_rate": _safe_rate(
                    answers["control"]["knowledge_trapped"], control_answers
                ),
            },
        },
        "videos": {
            "conflict": {
                "total": conflict_videos,
                "labels": {
                    label: videos["conflict"][label] for label in sorted(VERDICTS)
                },
                "grounded_video_rate": _safe_rate(
                    videos["conflict"]["context_grounded"], conflict_videos
                ),
                "trapped_video_rate": _safe_rate(
                    videos["conflict"]["knowledge_trapped"], conflict_videos
                ),
            },
            "control": {
                "total": control_videos,
                "labels": {
                    label: videos["control"][label] for label in sorted(VERDICTS)
                },
                "grounded_video_rate": _safe_rate(
                    videos["control"]["context_grounded"], control_videos
                ),
                "trapped_video_rate": _safe_rate(
                    videos["control"]["knowledge_trapped"], control_videos
                ),
            },
        },
    }


def _effort_name(effort: str | None) -> str:
    return "none" if effort is None else effort


def _newer(candidate: dict[str, Any], current: dict[str, Any] | None) -> bool:
    if current is None:
        return True
    return (
        str(candidate.get("timestamp", "")),
        str(candidate.get("run_id", "")),
    ) >= (
        str(current.get("timestamp", "")),
        str(current.get("run_id", "")),
    )


def build_summary(
    case_paths: list[Path],
    *,
    qa_model: str,
    input_mode: str,
    effort: str | None,
    work_title_prefix: bool | None,
    based: bool = False,
    filter_mode: str = "all",
    index: ReportIndex | None = None,
) -> dict[str, Any]:
    index = index or ReportIndex((p, load_case(p)) for p in case_paths)
    if input_mode == "question_only":
        latest_questions: dict[tuple[str, str, str], dict[str, Any]] = {}
        for case_path in case_paths:
            case = index.load(case_path)
            for video, question in conflict_question_scopes(case):
                state = question_filter_state(case, video, question, qa_model, effort)
                for result in ([state['result']] if state['status'] in ('passed', 'failed') else []):
                    if (
                        result.get("question_id") != question["question_id"]
                        or not qa_result_matches(
                            result,
                            model=qa_model,
                            input_selection="question_only",
                            efforts={effort},
                            work_title_prefix=None,
                        )
                        or not isinstance(result.get("judgment"), dict)
                    ):
                        continue
                    key = (case["case_id"], scope_id(video), question["question_id"])
                    previous = latest_questions.get(key)
                    if not _newer(result, previous):
                        continue
                    judgment = dict(result["judgment"])
                    judgment["verdict"] = canonical_verdict(
                        judgment["verdict"]
                    )
                    latest_questions[key] = {**result, "judgment": judgment}

        answer_counts: Counter[str] = Counter()
        case_counts: dict[str, Counter[str]] = defaultdict(Counter)
        for (case_id, _, _), result in latest_questions.items():
            verdict = result["judgment"]["verdict"]
            answer_counts[verdict] += 1
            case_counts[case_id][verdict] += 1
        total = sum(answer_counts.values())
        return {
            "generated_at": utc_now(),
            "qa_model": qa_model,
            "input": "question_only",
            "thinking_effort": _effort_name(effort),
            "answers": {
                "control": {
                    "total": total,
                    "labels": {
                        label: answer_counts[label] for label in sorted(VERDICTS)
                    },
                    "grounded_answer_rate": _safe_rate(
                        answer_counts["context_grounded"], total
                    ),
                    "trapped_answer_rate": _safe_rate(
                        answer_counts["knowledge_trapped"], total
                    ),
                }
            },
            "cases": {
                case_id: {
                    "control": {
                        "answers": sum(counts.values()),
                        "labels": {
                            label: counts[label] for label in sorted(VERDICTS)
                        },
                    }
                }
                for case_id, counts in sorted(case_counts.items())
            },
        }

    latest: dict[tuple[str, str, str], tuple[str, dict[str, Any]]] = {}
    gates = {}
    excluded_answers = set()
    for case_path in case_paths:
        case = index.load(case_path)
        for video in case["videos"]:
            if not video_selected(video, input_mode):
                continue
            questions = {q['question_id']: q for q in video_case_context(case, video)['questions']}
            if filter_mode == "passed":
                for question in questions.values():
                    key = (case['case_id'], scope_id(video), question['question_id'])
                    if key not in gates:
                        gates[key] = index.gate(case, video, question, qa_model, effort)
            for result in video["qa_results"]:
                if not qa_result_matches(
                    result,
                    model=qa_model,
                    input_selection=input_mode,
                    efforts={effort},
                    work_title_prefix=work_title_prefix,
                    based=based,
                ) or not index.judgment_current(case, video, result):
                    continue
                key = (case["case_id"], video["video_id"], result["question_id"])
                if filter_mode == "passed":
                    gate = gates[(case['case_id'], scope_id(video), result['question_id'])]
                    if not gate['passed']:
                        excluded_answers.add(key)
                        continue
                previous = latest.get(key)
                if previous is not None and not _newer(result, previous[1]):
                    continue
                judgment = dict(result["judgment"])
                judgment["verdict"] = canonical_verdict(judgment["verdict"])
                latest[key] = (
                    video["role"],
                    {**result, "judgment": judgment},
                )

    answer_counts = {"conflict": Counter(), "control": Counter()}
    grouped_videos: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for key, (role, result) in latest.items():
        verdict = result["judgment"]["verdict"]
        answer_counts[role][verdict] += 1
        grouped_videos[(key[0], key[1], role)].append(verdict)

    video_counts = {"conflict": Counter(), "control": Counter()}
    case_counts: dict[str, dict[str, Counter[str]]] = defaultdict(
        lambda: {"conflict": Counter(), "control": Counter()}
    )
    for (case_id, _, role), verdicts in grouped_videos.items():
        verdict = aggregate_video_verdict(verdicts)
        video_counts[role][verdict] += 1
        case_counts[case_id][role][verdict] += 1
    overall = _summarize_counts(answer_counts, video_counts)
    summary = {
        "generated_at": utc_now(),
        "video_scope": "all",
        "qa_model": qa_model,
        "input": input_mode,
        "thinking_effort": _effort_name(effort),
        "answers": overall["answers"],
        "videos": overall["videos"],
        "cases": {
            case_id: {
                role: {
                    "videos": sum(counts[role].values()),
                    "labels": {
                        label: counts[role][label] for label in sorted(VERDICTS)
                    },
                }
                for role in ("conflict", "control")
            }
            for case_id, counts in sorted(case_counts.items())
        },
    }
    if work_title_prefix is not None:
        summary["work_title_prefix"] = work_title_prefix
    summary["based"] = based
    summary['filter'] = filter_mode
    if filter_mode == 'passed':
        reasons = Counter(g['reason'] for g in gates.values())
        summary['filter_gate'] = {
            'unit': 'case + question_scope + question_id + model + thinking_effort',
            'total_questions': len(gates), 'passed_questions': reasons['passed'],
            'excluded_questions': len(gates) - reasons['passed'],
            'excluded_judged_answers': len(excluded_answers),
            'reasons': dict(sorted(reasons.items())),
            'questions': [gates[key] for key in sorted(gates)],
        }
    return summary


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else "" if value is None else str(value)


def _markdown_value(value: Any) -> str:
    return _text(value).replace("\r\n", "\n").replace("\r", "\n").replace(
        "\n", "<br>"
    )


def _local_video_link(local_path: Any) -> str:
    display = _text(local_path).replace("\\", "/")
    if not display:
        return ""
    supplied = Path(display)
    resolved = supplied if supplied.is_absolute() else PROJECT_ROOT / supplied
    target = f"potplayer://{resolved.resolve(strict=False).as_posix()}"
    label = display.replace("[", r"\[").replace("]", r"\]")
    return f"[{label}]({target})"


def _latest_results(
    results: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    latest: dict[str | None, dict[str, Any]] = {}
    for result in results:
        effort = qa_result_thinking_effort(result)
        if _newer(result, latest.get(effort)):
            latest[effort] = result
    return [latest[key] for key in sorted(latest, key=lambda value: str(value))]


def build_markdown(
    case_paths: list[Path],
    *,
    qa_model: str,
    input_mode: str,
    efforts: set[str | None],
    work_title_prefix: bool | None,
    based: bool = False,
    filter_mode: str = "all",
    index: ReportIndex | None = None,
    summaries: dict | None = None,
) -> str:
    index = index or ReportIndex((p, load_case(p)) for p in case_paths)
    effort_names = ", ".join(
        _effort_name(item) for item in sorted(efforts, key=str)
    )
    lines = [
        (
            "# Question Only Control Results"
            if input_mode == "question_only"
            else "# Control Video Results" if input_mode == "control"
            else f"# {input_mode.title()} Knowledge Conflict Results"
        ),
        "",
        f"**QA model:** {_markdown_value(qa_model)}",
        "",
        f"**Thinking efforts:** {effort_names}",
        "",
    ]
    if work_title_prefix is not None:
        prefix_name = "with_prefix" if work_title_prefix else "no_prefix"
        lines.extend([f"**Work-title prefix:** {prefix_name}", ""])
    if input_mode != "question_only":
        lines.extend([f"**Based prompt:** {'enabled' if based else 'disabled'}", ""])
    if summaries is None:
        summaries = {
            effort: build_summary(
                case_paths, qa_model=qa_model, input_mode=input_mode, effort=effort,
                work_title_prefix=work_title_prefix, based=based,
                filter_mode=filter_mode, index=index,
            )
            for effort in efforts
        }
    if filter_mode == 'passed':
        lines.extend(['**Question filter:** question-only must pass for each question scope/model/effort.', ''])
        for effort in sorted(efforts, key=str):
            stats = summaries[effort]['filter_gate']
            lines.extend([f"- {_effort_name(effort)}: {stats['passed_questions']}/{stats['total_questions']} questions passed; "
                          f"{stats['excluded_judged_answers']} judged answers excluded. Reasons: {stats['reasons']}", ''])
    columns = ["Effort", "Role", "Answers", "grounded_answer_rate", "trapped_answer_rate"]
    if input_mode != "question_only":
        columns.extend(["Videos", "grounded_video_rate", "trapped_video_rate"])
    lines.extend([
        "## Summary", "",
        "Rates use all valid judged samples for each role, including ambiguous labels; no samples means null.", "",
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---", "---", *(["---:"] * (len(columns) - 2))]) + " |",
    ])
    for effort in sorted(efforts, key=str):
        summary = summaries[effort]
        for role, answers in summary["answers"].items():
            values = [_effort_name(effort), role, answers["total"],
                      answers["grounded_answer_rate"], answers["trapped_answer_rate"]]
            if input_mode != "question_only":
                videos = summary["videos"][role]
                values.extend([videos["total"], videos["grounded_video_rate"], videos["trapped_video_rate"]])
            lines.append("| " + " | ".join(
                "null" if value is None else f"{value:.6f}" if isinstance(value, float) else str(value)
                for value in values
            ) + " |")
    lines.append("")
    for path in case_paths:
        case = index.load(path)
        title = _markdown_value(case["title"]).replace("#", r"\#")
        lines.extend([f"## {title}", ""])
        if input_mode == "question_only":
            for video, question in conflict_question_scopes(case):
                matching = []
                for effort in sorted(efforts, key=str):
                    state = question_filter_state(case, video, question, qa_model, effort)
                    if state['status'] in ('unjudged', 'passed', 'failed'):
                        matching.append(state['result'])
                if not matching:
                    continue
                lines.extend(
                    [
                        f"### Question `{scope_id(video)}/{question['question_id']}`",
                        "",
                        f"**Question:** {_markdown_value(question['text_en'])}",
                        "",
                    ]
                )
                for result_index, result in enumerate(matching, start=1):
                    judgment = result.get("judgment")
                    judgment = judgment if isinstance(judgment, dict) else {}
                    verdict = canonical_verdict(judgment.get("verdict", ""))
                    lines.extend(
                        [
                            f"#### QA result {result_index}",
                            "",
                            f"- **QA model:** {_markdown_value(result.get('model'))}",
                            "- **Thinking effort:** "
                            f"{_effort_name(qa_result_thinking_effort(result))}",
                        ]
                    )
                    if result.get("effective_reasoning_effort") is not None:
                        lines.append(
                            "- **Effective reasoning effort:** "
                            f"{_markdown_value(result['effective_reasoning_effort'])}"
                        )
                    lines.extend(
                        [
                            f"- **Raw answer:** {_markdown_value(result.get('raw_answer'))}",
                            "- **Final answer (judged):** "
                            f"{_markdown_value(result.get('final_answer'))}",
                            f"- **Verdict:** {_markdown_value(verdict)}",
                            "- **Confidence:** "
                            f"{_markdown_value(judgment.get('confidence'))}",
                            "",
                        ]
                    )
            continue
        question_groups = []
        for video in case["videos"]:
            if not video_selected(video, input_mode):
                continue
            for question in video_case_context(case, video)["questions"]:
                group = next((item for item in question_groups if item[0] == question), None)
                if group is None:
                    group = (question, [])
                    question_groups.append(group)
                group[1].append(video)
        for question_index, (question, question_videos) in enumerate(question_groups, start=1):
            if filter_mode == 'passed' and not any(
                index.gate(case, v, question, qa_model, effort)['passed']
                for v in question_videos for effort in efforts
            ):
                continue
            lines.extend(
                [
                    f"### Question {question_index}",
                    "",
                    f"**Question:** {_markdown_value(question['text_en'])}",
                    "",
                ]
            )
            for video in question_videos:
                matching = _latest_results(
                    result
                    for result in video["qa_results"]
                    if result.get("question_id") == question["question_id"]
                    and index.qa_current(case, video, result)
                    and (filter_mode != 'passed' or (
                        index.judgment_current(case, video, result)
                        and index.gate(case, video, question, qa_model,
                                          qa_result_thinking_effort(result))['passed']))
                    and qa_result_matches(
                        result,
                        model=qa_model,
                        input_selection=input_mode,
                        efforts=efforts,
                        work_title_prefix=work_title_prefix,
                        based=based,
                    )
                )
                if (input_mode == "description" or filter_mode == 'passed') and not matching:
                    continue
                lines.extend([f"#### Video `{video['video_id']}`", ""])
                if input_mode == "description":
                    lines.extend(
                        [
                            "**Context:** "
                            f"{_markdown_value(matching[-1].get('context_text_en'))}",
                            "",
                        ]
                    )
                else:
                    lines.extend(
                        [f"**Local file:** {_local_video_link(video['local_path'])}", ""]
                    )
                for result_index, result in enumerate(matching or [{}], start=1):
                    judgment = result.get("judgment") if index.judgment_current(case, video, result) else None
                    judgment = judgment if isinstance(judgment, dict) else {}
                    verdict = canonical_verdict(judgment.get("verdict", ""))
                    effort_display = (
                        _effort_name(qa_result_thinking_effort(result))
                        if result
                        else ""
                    )
                    lines.extend(
                        [
                            f"##### QA result {result_index}",
                            "",
                            f"- **QA model:** {_markdown_value(result.get('model'))}",
                            f"- **Thinking effort:** {effort_display}",
                        ]
                    )
                    if result.get("effective_reasoning_effort") is not None:
                        lines.append(
                            "- **Effective reasoning effort:** "
                            f"{_markdown_value(result['effective_reasoning_effort'])}"
                        )
                    lines.extend(
                        [
                            f"- **Raw answer:** {_markdown_value(result.get('raw_answer'))}",
                            "- **Final answer (judged):** "
                            f"{_markdown_value(result.get('final_answer'))}",
                            f"- **Verdict:** {_markdown_value(verdict)}",
                            f"- **Confidence:** {_markdown_value(judgment.get('confidence'))}",
                            "",
                        ]
                    )
    return "\n".join(lines).rstrip() + "\n"


def _discover_efforts(
    case_paths: list[Path],
    *,
    qa_model: str,
    input_mode: str,
    work_title_prefix: bool | None,
    based: bool = False,
    index: ReportIndex | None = None,
) -> tuple[str | None, ...]:
    index = index or ReportIndex((p, load_case(p)) for p in case_paths)
    supported_efforts = expand_thinking_efforts(["all"], qa_model)
    default_efforts = expand_thinking_efforts(None, qa_model)
    observed: set[str | None] = set()
    for path in case_paths:
        case = index.load(path)
        if input_mode == "question_only":
            for video, question in conflict_question_scopes(case):
                for effort in supported_efforts:
                    state = question_filter_state(case, video, question, qa_model, effort)
                    if state['status'] in ('passed', 'failed'):
                        observed.add(effort)
            continue
        for video in case["videos"]:
            if not video_selected(video, input_mode):
                continue
            for result in video["qa_results"]:
                effort = qa_result_thinking_effort(result)
                if (
                    qa_result_matches(
                        result,
                        model=qa_model,
                        input_selection=input_mode,
                        efforts=set(supported_efforts),
                        work_title_prefix=work_title_prefix,
                        based=based,
                    )
                    and index.judgment_current(case, video, result)
                    and effort in supported_efforts
                ):
                    observed.add(effort)
    selected = tuple(
        effort for effort in supported_efforts if effort in observed
    )
    return selected or default_efforts


def _require_video_prefix_metadata(
    case_paths: list[Path],
    *,
    qa_model: str,
    input_mode: str,
    based: bool,
    efforts: set[str | None],
    index: ReportIndex,
) -> None:
    for path in case_paths:
        case = index.load(path)
        for video in case["videos"]:
            if not video_selected(video, input_mode):
                continue
            for result in video["qa_results"]:
                if (qa_result_matches(result, input_selection=input_mode, model=qa_model,
                                      efforts=efforts, based=based)
                        and index.qa_current(case, video, result)
                        and qa_result_work_title_prefix(result) is None):
                    raise PipelineError(
                        f"QA result {case['case_id']}/{video['video_id']}/"
                        f"{result['question_id']} in {path} has no work_title_prefix. "
                        "Backfill it with true or false before summarizing video results."
                    )


def _fairy_video_prefix_name(args: argparse.Namespace) -> str | None:
    if args.input not in ("video", "control") or args.group != FAIRY_TALE_GROUP:
        return None
    return "with_prefix" if args.with_work_title_prefix else "no_prefix"


def command_summarize(args: argparse.Namespace) -> int:
    from .runtime import (
        Runtime,
    )
    dataset_dir = grouped_dir(args.dataset_dir, args.group)
    paths = iter_case_paths(dataset_dir, args.case_id)
    with Runtime(paths) as runtime:
        index = ReportIndex(runtime.snapshot(paths, workers=args.summary_workers))
    print('Report uses a consistent case snapshot; concurrent QA may still be incomplete.')
    based_condition = bool(getattr(args, "based", False))
    if args.input == "question_only":
        for path in paths:
            require_question_only_compatible(index.load(path))
    work_title_prefix = work_title_prefix_condition(
        args.group,
        args.input,
        args.with_work_title_prefix,
    )
    requested = list(args.thinking_effort or [])
    explicit_efforts = bool(requested and 'all' not in requested)
    selected_efforts = expand_thinking_efforts(requested if explicit_efforts else ['all'], args.qa_model)
    if work_title_prefix is not None:
        _require_video_prefix_metadata(paths, qa_model=args.qa_model, input_mode=args.input,
                                       based=based_condition, efforts=set(selected_efforts), index=index)
    efforts = selected_efforts if explicit_efforts else _discover_efforts(
        paths, qa_model=args.qa_model, input_mode=args.input,
        work_title_prefix=work_title_prefix, based=based_condition, index=index,
    )
    model_slug = QA_MODEL_SLUGS[args.qa_model]
    result_dir = grouped_dir(RESULTS_DIR, args.group) / model_slug
    prefix_name = _fairy_video_prefix_name(args)
    filter_mode = getattr(args, 'filter_mode', 'all')
    summaries = {}
    report_parts = [model_slug, args.input]
    if based_condition:
        report_parts.append('based')
    if prefix_name is not None:
        report_parts.append(prefix_name)
    if filter_mode == 'passed':
        report_parts.append('filter_passed')
    for effort in efforts:
        output = result_dir / ('_'.join([*report_parts, _effort_name(effort), 'summary']) + '.json')
        summaries[effort] = build_summary(
                paths,
                qa_model=args.qa_model,
                input_mode=args.input,
                effort=effort,
                work_title_prefix=work_title_prefix,
                based=based_condition,
                filter_mode=filter_mode,
                index=index,
        )
        atomic_write_json(output, summaries[effort])
        print(f"Wrote summary: {output}")

    report_output = result_dir / ("_".join(report_parts) + "_report.md")
    atomic_write_text(
        report_output,
        build_markdown(
            paths,
            qa_model=args.qa_model,
            input_mode=args.input,
            efforts=set(efforts),
            work_title_prefix=work_title_prefix,
            based=based_condition,
            filter_mode=filter_mode,
            index=index,
            summaries=summaries,
        ),
    )
    print(f"Wrote report: {report_output}")
    return 0
