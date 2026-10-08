"""Independent reports for human QA answers and human judge answers."""
from __future__ import annotations
import argparse
import collections
import csv
import json
from pathlib import Path
from .common import read_tasks, LABELS, now, read_jsonl, verify_run, write_json, write_jsonl
from .score import scores_for
from .storage import Store

def ratio(a,b):
    return a/b if b else None

def canonical(value):
    return "context_grounded" if value == "video_grounded" else value

def qa_stats(tasks,state,scores):
    answered=sum((t["id"],"answer") in state for t in tasks)
    classified=[scores[t["id"]] for t in tasks if t["id"] in scores]
    counts=collections.Counter(s["label"] for s in classified)
    return {"sampled":len(tasks),"answered":answered,"pending_answers":len(tasks)-answered,
            "blocked_inputs":sum(bool(t["errors"]) for t in tasks),"scored":len(classified),
            "pending_scoring":answered-len(classified),"label_counts":{l:counts[l] for l in LABELS},
            "knowledge_trapped_rate":ratio(counts["knowledge_trapped"],len(classified)),
            "scoring_methods":dict(collections.Counter(s["method"] for s in classified))}

def judge_stats(tasks,state):
    compared=agreed=submitted=0
    confusion={a:{b:0 for b in LABELS} for a in LABELS}
    scope=collections.Counter()
    for t in tasks:
        d=state.get((t["id"],"judge"))
        if not d:
            continue
        submitted+=1
        human=d.get("answer") or d.get("label")
        llm=canonical(((t.get("result") or {}).get("judgment") or {}).get("verdict"))
        if t["errors"] or human not in LABELS or llm not in LABELS:
            continue
        compared+=1
        agreed+=human==llm
        confusion[human][llm]+=1
        scope[d.get("material_scope","legacy")]+=1
    return {"sampled_qa":len({t["qa_key"] for t in tasks}),"expected_decisions":len(tasks),
            "submitted":submitted,"pending":len(tasks)-submitted,
            "blocked_inputs":sum(bool(t["errors"]) for t in tasks),
            "compared":compared,"agreed":agreed,"agreement":ratio(agreed,compared),
            "confusion_human_rows_llm_columns":confusion,"material_scope":dict(scope)}

def percent(value):
    return "—" if value is None else f"{value:.1%}"

def mean(values):
    values=[v for v in values if v is not None]
    return sum(values)/len(values) if values else None

def report(run,annotator=None):
    run=Path(run).resolve()
    manifest=verify_run(run)
    tasks=read_tasks(run)
    store=Store(run/"annotations.sqlite",tasks)
    with store.connection() as db:
        people=[r[0] for r in db.execute("SELECT DISTINCT annotator FROM submissions ORDER BY annotator")]
    if annotator:
        store.check_annotator(annotator)
        people=[annotator]
    people=people or ["not_started"]
    output={"created_at":now(),"run":run.name,"sampling":manifest["inventory"],
            "profiles":manifest["profiles"],"annotators":{},
            "notes":["QA and judge are independent; each person submits only an answer.",
                     "Human QA answer categories are scored automatically, not a second human annotation.",
                     "Unscored or missing answers never count as successful answers.",
                     "New judge submissions use llm_judge_text_only; historical full_materials submissions included video/full output. Check material_scope before combining.",
                     "20 QA per group is an audit, not proof of zero population error."]}
    rows=[]
    qa_lines=["# 1 · 人工回答 QA",""]
    judge_lines=["# 2 · 人工 Judge",""]
    for who in people:
        state=store.state(who);scores=scores_for(store,who);groups={}
        for g in manifest["inventory"]:
            qa=[t for t in tasks if t["kind"]=="qa" and t["group"]==g]
            judge=[t for t in tasks if t["kind"]=="judge" and t["group"]==g]
            groups[g]={"qa":qa_stats(qa,state,scores),"judge":judge_stats(judge,state),
                       "judge_by_profile":{pid:judge_stats([t for t in judge if t["profile_id"]==pid],state)
                                           for pid in manifest["profiles"][g]}}
        overall_qa=qa_stats([t for t in tasks if t["kind"]=="qa"],state,scores)
        overall_judge=judge_stats([t for t in tasks if t["kind"]=="judge"],state)
        output["annotators"][who]={"groups":groups,"overall_qa":overall_qa,"overall_judge":overall_judge,
            "macro_group_qa_trapped_rate":mean(v["qa"]["knowledge_trapped_rate"] for v in groups.values()),
            "macro_group_judge_agreement":mean(v["judge"]["agreement"] for v in groups.values())}
        qa_lines += [f"## {who}","", "| Group | 抽样 | 已回答 | 后台已评分 | 待评分 | knowledge-trapped / 已评分 |",
                     "|---|---:|---:|---:|---:|---:|"]
        judge_lines += [f"## {who}","","| Group | 条件 | 抽样 QA | 已判定 | 缺失输入 | 可比较 | 一致率 |",
                        "|---|---|---:|---:|---:|---:|---:|"]
        for g,v in groups.items():
            q=v["qa"]
            qa_lines.append(f"| {g} | {q['sampled']} | {q['answered']} | {q['scored']} | {q['pending_scoring']} | {percent(q['knowledge_trapped_rate'])} |")
            for pid,j in v["judge_by_profile"].items():
                judge_lines.append(f"| {g} | {pid} | {j['sampled_qa']} | {j['submitted']} | {j['blocked_inputs']} | {j['compared']} | {percent(j['agreement'])} |")
        qa_lines+=["",f"合并 knowledge-trapped 比例：{percent(overall_qa['knowledge_trapped_rate'])}。",""]
        judge_lines+=["",f"合并一致率：{percent(overall_judge['agreement'])}。",""]
        for t in tasks:
            d=state.get((t["id"],"answer" if t["kind"]=="qa" else "judge"),{})
            human=d.get("answer") or d.get("label")
            automatic=scores.get(t["id"])
            llm=canonical(((t.get("result") or {}).get("judgment") or {}).get("verdict"))
            comparable=t["kind"]=="judge" and human in LABELS and llm in LABELS and not t["errors"]
            rows.append({"annotator":who,"task_id":t["id"],"kind":t["kind"],"group":t["group"],
                         "qa_key":t["qa_key"],"answer":human,"profile_id":t.get("profile_id"),
                         "automatic_score":automatic,"llm_judge":llm,
                         "agreed":human==llm if comparable else None,"errors":t["errors"]})
    qa_lines += ["自动评分仅对可评分答案计算比例，待评分不当作成功。开放回答的语义评分使用独立 score 命令；不是人工二次归类。",""]
    judge_lines += ["新版人工 Judge 与 LLM Judge 使用相同文本输入。旧记录 full_materials 使用过视频与完整回答，新记录标为 llm_judge_text_only；请按 material_scope 区分实验口径。完整条件与混淆矩阵见 summary.json。",""]
    destination=run/"reports"/(annotator or "all")
    destination.mkdir(parents=True,exist_ok=True)
    write_json(destination/"summary.json",output)
    write_jsonl(destination/"annotations.jsonl",rows)
    write_jsonl(destination/"qa_answers.jsonl",[r for r in rows if r["kind"]=="qa"])
    write_jsonl(destination/"judge_answers.jsonl",[r for r in rows if r["kind"]=="judge"])
    write_jsonl(destination/"disagreements.jsonl",[r for r in rows if r["agreed"] is False or r["errors"]])
    (destination/"qa_report.md").write_text("\n".join(qa_lines),encoding="utf-8")
    (destination/"judge_report.md").write_text("\n".join(judge_lines),encoding="utf-8")
    (destination/"report.md").write_text("# 人工评测\n\n[1 · QA 报告](qa_report.md)\n\n[2 · Judge 报告](judge_report.md)\n",encoding="utf-8")
    if rows:
        with (destination/"annotations.csv").open("w",encoding="utf-8-sig",newline="") as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader()
            for row in rows:
                cells={k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in row.items()}
                writer.writerow({k:"'"+v if isinstance(v,str) and v.startswith(("=","+","-","@","\t","\r")) else v for k,v in cells.items()})
    print(f"Reports: {destination}")
    return output

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",required=True,type=Path)
    parser.add_argument("--annotator")
    args=parser.parse_args();report(args.run,args.annotator)

if __name__=="__main__":
    main()
