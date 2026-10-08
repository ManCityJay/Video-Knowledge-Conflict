"use strict";
const $=id=>document.getElementById(id);
const names={classic_fairy_tale_film_conflicts:"童话影视",classic_physics_chemistry_experiments:"物理化学",mathematics_algorithm_conflicts:"数学算法",real_world_commonsense_conflicts:"日常常识"};
const kind=location.pathname.replaceAll("/","");
let who=localStorage.getItem("human-audit-annotator");
if(!who){who="annotator_"+crypto.randomUUID();localStorage.setItem("human-audit-annotator",who);}
let index=null,current=null,group="",visible=[],dirty=false,timer=null,saving=Promise.resolve(),transition=false;
function notice(message){$("notice").textContent=message;$("notice").hidden=false;setTimeout(()=>$("notice").hidden=true,5000);}
async function api(path,body){const opts=body?{method:"POST",headers:{"Content-Type":"application/json","X-Audit-Token":index.token},body:JSON.stringify(body)}:{};const r=await fetch(path,opts);const data=await r.json();if(!r.ok)throw Error(data.error||"请求失败");return data;}
function query(path,extra={}){return path+"?"+new URLSearchParams({annotator:who,kind,...extra});}
function text(parent,tag,value,cls=""){const el=document.createElement(tag);el.textContent=value;el.className=cls;parent.append(el);return el;}
function block(parent,title,value){text(parent,"h3",title);text(parent,"div",value||"","text");}
function details(parent,title,value){const d=document.createElement("details");text(d,"summary",title);text(d,"pre",typeof value==="string"?value:JSON.stringify(value,null,2));parent.append(d);}
function field(){return $(kind==="qa"?"answer":"judge-answer");}
function submitted(t){return t.done;}
function list(){
 visible=index.items.filter(t=>t.group===group);
 $("task-list").replaceChildren();
 visible.forEach((t,i)=>{const b=text($("task-list"),"button",(t.done?"✓ ":t.errors?"! ":"")+(i+1), "row"+(current?.id===t.id?" active":"")+(t.done?" done":""));b.onclick=()=>load(t.id).catch(e=>notice(e.message));});
 $("groups").replaceChildren();
 Object.keys(index.inventory).forEach(g=>{const items=index.items.filter(t=>t.group===g);const b=text($("groups"),"button",(names[g]||g)+" "+items.filter(submitted).length+"/"+items.length,g===group?"active":"");b.onclick=async()=>{try{await flush();group=g;list();if(visible.length)await load((visible.find(t=>!t.done&&!t.errors)||visible[0]).id);else{current=null;$("task").hidden=true;$("empty").hidden=false;}}catch(e){notice(e.message);}};});
 $("progress").textContent="已完成 "+index.items.filter(submitted).length+" / "+index.items.length;
}
async function refresh(){index=await api(query("/api/index"));if(!group)group=Object.keys(index.inventory)[0]||"";list();}
async function flush(){
 clearTimeout(timer);await saving;
 if(!current||!dirty||current.submission||current.errors.length)return;
 const payload={annotator:who,task_id:current.id,stage:current.stage,data:{answer:field().value}};dirty=false;
 saving=api("/api/draft",payload).then(()=>{$("save-state").textContent="草稿已保存";}).catch(e=>{dirty=true;throw e;});
 try{await saving;}finally{saving=Promise.resolve();}
}
function changed(){dirty=true;$("save-state").textContent="正在保存…";clearTimeout(timer);timer=setTimeout(()=>flush().catch(e=>notice(e.message)),600);}
function render(){
 const t=current;$("task").hidden=false;$("empty").hidden=true;const pos=visible.findIndex(v=>v.id===t.id);
 $("position").textContent=(names[t.group]||t.group)+" · "+(pos+1)+" / "+visible.length;
 $("missing").hidden=!t.errors.length;$("missing").textContent=t.errors.length?"该样本缺少可用材料，保留抽样记录，无需作答。":"";
 const m=$("materials"),more=$("more-materials");m.replaceChildren();more.replaceChildren();
 if(t.has_video){const v=document.createElement("video");v.controls=true;v.preload="metadata";v.src=query("/media/"+t.id);m.append(v);}
 if(kind==="qa"){
  block(m,"Question",t.qa_input.question);
  if(t.qa_input.input_mode==="description")block(m,"Context / 完整提示词",t.qa_input.prompt);
  else details(m,"完整提示词",t.qa_input.prompt);
 }else if(t.judge_input){
  block(m,"Question",t.judge_input.input.question);
  block(m,"模型 Answer",t.judge_input.input.final_answer);
  block(m,"视频角色（文本）",t.judge_input.input.video_role);
  block(m,"正常事实",t.judge_input.input.normal_fact);
  block(m,"预期视频事实（文本）",t.judge_input.input.intended_video_fact);
  block(m,"冲突情境参考答案",t.judge_input.input.conflict_video_reference);
  block(m,"正常情境参考答案",t.judge_input.input.normal_control_reference);
  details(m,"判定规则",t.judge_input.system);
  details(m,"完整上下文",t.judge_input.input);
  details(m,"输出格式",t.judge_input.response_schema);
 }
 if(t.qa_input)details(more,"模型完整输入",t.qa_input.messages);

 if(t.warnings.length)details(more,"输入来源说明",t.warnings.join("\n"));
 $("answer").hidden=kind!=="qa";$("judge-answer").hidden=kind!=="judge";
 const saved=t.submission||t.draft;field().value=saved?.answer||saved?.label||"";
 field().disabled=!!t.submission||!!t.errors.length;$("submit").disabled=field().disabled;
 $("save-state").textContent=t.submission?"已提交":Object.keys(t.draft).length?"已恢复草稿":"";

 $("prev").disabled=pos<=0;$("next").disabled=pos>=visible.length-1;
 dirty=false;list();
}
async function load(id){if(transition)return;transition=true;try{await flush();current=await api(query("/api/task",{id}));render();}finally{transition=false;}}
$("answer-form").onsubmit=async e=>{e.preventDefault();if(transition)return;transition=true;$("answer-form").inert=true;try{await flush();const old=current.id;await api("/api/submit",{annotator:who,task_id:old,stage:current.stage,data:{answer:field().value}});await refresh();const pos=visible.findIndex(t=>t.id===old);const next=visible.slice(pos+1).find(t=>!t.done&&!t.errors)||visible.find(t=>!t.done&&!t.errors);current=await api(query("/api/task",{id:next?next.id:old}));render();notice("已保存");}catch(e){notice(e.message);}finally{transition=false;$("answer-form").inert=false;}};
for(const id of ["answer","judge-answer"])$(id).addEventListener("input",changed);
for(const [id,step] of [["prev",-1],["next",1]])$(id).onclick=()=>{const pos=visible.findIndex(t=>t.id===current?.id)+step;if(pos>=0&&pos<visible.length)load(visible[pos].id).catch(e=>notice(e.message));};
document.querySelectorAll("header a").forEach(a=>a.addEventListener("click",async e=>{if(dirty){e.preventDefault();try{await flush();location.href=a.href;}catch(err){notice(err.message);}}}));
window.addEventListener("beforeunload",e=>{if(dirty){e.preventDefault();e.returnValue="";}});
function showIdentity(){ $("current-annotator").textContent=who; $("annotator-input").value=who; }
async function changeIdentity(rename){
 if(transition)return;
 const target=$("annotator-input").value.trim();
 if(!target){notice("请填写姓名或编号");return;}
 transition=true;
 document.querySelectorAll(".identity button").forEach(b=>b.disabled=true);
 $("answer-form").inert=true;
 try{
  await flush();
  const next=await api("/api/index?"+new URLSearchParams({annotator:target,...(["qa","judge"].includes(kind)?{kind}:{})}));
  if(rename)await api("/api/rename",{annotator:who,new_annotator:target});
  who=target;localStorage.setItem("human-audit-annotator",who);showIdentity();current=null;dirty=false;
  if(["qa","judge"].includes(kind)){
   await refresh();
   if(visible.length){current=await api(query("/api/task",{id:(visible.find(t=>!t.done&&!t.errors)||visible[0]).id}));render();}
  }else{index=next;}
  notice(rename?"当前进度已改名并保存":"已切换评测者并恢复进度");
 }catch(e){notice(e.message);}finally{transition=false;$("answer-form").inert=false;document.querySelectorAll(".identity button").forEach(b=>b.disabled=false);}
}
$("identity-form").onsubmit=e=>{e.preventDefault();changeIdentity(false);};
$("rename-annotator").onclick=()=>changeIdentity(true);
async function start(){showIdentity();if(!["qa","judge"].includes(kind)){$("home").hidden=false;index=await api("/api/index?"+new URLSearchParams({annotator:who}));return;}$("workspace").hidden=false;$("title").textContent=kind==="qa"?"1 · 回答 conflict QA":"2 · 人工 Judge";await refresh();if(visible.length)await load((visible.find(t=>!t.done&&!t.errors)||visible[0]).id);else $("empty").hidden=false;}
start().catch(e=>notice(e.message));
