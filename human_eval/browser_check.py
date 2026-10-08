"""Optional browser smoke test. Requires Playwright; annotations use a temp run."""
from __future__ import annotations

import argparse
import shutil
import tempfile
import threading
from pathlib import Path

from .app import Audit, make_server
from .common import HERE, file_hash, read_jsonl, write_json, write_jsonl


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    args = parser.parse_args()
    source = args.run.resolve()
    rows = read_jsonl(source / "tasks.jsonl")
    tasks = ([t for t in rows if t["kind"] == "qa" and not t["errors"]][:2]
             + [t for t in rows if t["kind"] == "judge" and not t["errors"]][:2])
    if len(tasks) != 4:
        raise ValueError("Smoke test needs two complete QA and two complete judge items")
    for task in tasks:
        task["group"] = "browser_fixture"
    from playwright.sync_api import sync_playwright
    with tempfile.TemporaryDirectory(prefix="browser_check_", dir=HERE/"runs") as temporary:
        run = Path(temporary)
        (run/"media").mkdir()
        for task in tasks:
            asset = task["media"]["asset"]
            shutil.copyfile(source/asset, run/asset)
        write_jsonl(run/"tasks.jsonl", tasks)
        groups = {t["group"] for t in tasks}
        inventory = {g: {"qa_sampled": sum(t["group"] == g and t["kind"] == "qa" for t in tasks),
                         "judge_sampled": sum(t["group"] == g and t["kind"] == "judge" for t in tasks)} for g in groups}
        write_json(run/"manifest.json", {"files": {p.relative_to(run).as_posix():file_hash(p) for p in run.rglob("*") if p.is_file()}, "inventory":inventory})
        audit = Audit(run)
        server = make_server(audit, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(channel="msedge", headless=True)
                page = browser.new_page(viewport={"width":1440,"height":1100}, bypass_csp=True)
                errors=[]
                page.on("pageerror", lambda error: errors.append(str(error)))
                base=f"http://127.0.0.1:{server.server_port}"
                page.goto(base+"/judge")
                page.locator("#task").wait_for(state="visible")
                assert page.locator("#answer-form textarea:visible, #answer-form select:visible, #answer-form input:visible").count()==1
                assert page.locator("#judge-answer").is_visible()
                assert page.locator("video").count() == 0
                assert "模型完整回答" not in page.locator("#more-materials").inner_text()
                assert "模型完整输入" not in page.locator("#more-materials").inner_text()
                assert not page.locator("#more-materials").inner_text().find("LLM judge 结果")>=0
                # Judge is immediately available before answering any QA.
                who=page.evaluate("localStorage.getItem('human-audit-annotator')")
                assert not audit.store.state(who)
                # Rename legacy identity, persist a draft, switch people, restore from another browser.
                page.locator("#annotator-input").fill("张三")
                page.locator("#rename-annotator").click()
                page.wait_for_function("() => document.querySelector('#current-annotator').textContent === '张三'")
                page.locator("#judge-answer").select_option("knowledge_trapped")
                page.locator("#annotator-input").fill("reviewer02")
                page.locator("#use-annotator").click()
                page.wait_for_function("() => document.querySelector('#current-annotator').textContent === 'reviewer02' && document.querySelector('#judge-answer').value === ''")
                page.locator("#annotator-input").fill("张三")
                page.locator("#use-annotator").click()
                page.wait_for_function("() => document.querySelector('#judge-answer').value === 'knowledge_trapped'")
                other_context = browser.new_context()
                other = other_context.new_page()
                other.goto(base + "/judge")
                other.locator("#task").wait_for(state="visible")
                other.locator("#annotator-input").fill("张三")
                other.locator("#use-annotator").click()
                other.wait_for_function("() => document.querySelector('#judge-answer').value === 'knowledge_trapped'")
                other_context.close()
                who = "张三"

                for i in range(2):
                    page.locator("#judge-answer").select_option("context_grounded")
                    page.locator("#submit").click()
                    if i==0:
                        page.wait_for_function("document.querySelector('#position').textContent.includes('2 / 2')")
                    else:
                        page.wait_for_function("document.querySelector('#save-state').textContent==='已提交'")
                assert sum(stage=="judge" for _,stage in audit.store.state(who))==2
                assert sum(stage=="answer" for _,stage in audit.store.state(who))==0
                page.goto(base+"/qa")
                page.locator("#task").wait_for(state="visible")
                assert page.locator("#answer-form textarea:visible, #answer-form select:visible, #answer-form input:visible").count()==1
                assert page.locator("#answer").is_visible()
                assert page.locator("#reason, #evidence, #issue, #review-section, #label").count()==0
                page.wait_for_function("document.querySelector('video')?.readyState >= 1")
                page.locator("video").evaluate("v=>{v.muted=true;return v.play();}")
                page.wait_for_function("document.querySelector('video').currentTime>0.3")
                page.locator("video").evaluate("v=>v.pause()")
                page.locator("#answer").fill("Smoke test independent answer")
                page.wait_for_function("document.querySelector('#save-state').textContent==='草稿已保存'")
                page.reload()
                page.wait_for_function("document.querySelector('#answer').value==='Smoke test independent answer'")
                for i in range(2):
                    page.locator("#answer").fill("Smoke test answer without any extra fields")
                    page.locator("#submit").click()
                    if i==0:
                        page.wait_for_function("document.querySelector('#position').textContent.includes('2 / 2')")
                    else:
                        page.wait_for_function("document.querySelector('#save-state').textContent==='已提交'")
                assert sum(stage=="answer" for _,stage in audit.store.state(who))==2
                assert all(stage in {"answer","judge"} for _,stage in audit.store.state(who))
                assert not errors,errors
                screenshot = source/"reports"/"browser_check.png"
                page.screenshot(path=str(screenshot), full_page=True)
                browser.close()
                print("PASS: separate QA/Judge pages; judge works before QA; exactly one answer field per page; playable video; autosave/reload; submit and next; no JavaScript errors")
                print(f"Screenshot: {screenshot}")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    main()
