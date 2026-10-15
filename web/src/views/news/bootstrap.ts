import { filterStories, safeSourceUrl, type NewsArchive, type NewsStory } from "./archive";
import "./news.css";
import type { NewsNavigation, NewsNavigationItem } from "../chat/news-results";
let pending:Promise<void>|null=null;
let archive:NewsArchive|null=null;
let selectResult:((ids:string[])=>void)|null=null;
function node<K extends keyof HTMLElementTagNameMap>(tag:K,text:string,className="") { const el=document.createElement(tag);el.textContent=text;el.className=className;return el; }
function card(story:NewsStory) {
 const article=node("article","","news-card");article.id=`news-story-${story.id}`;article.dataset.newsId=story.id;article.tabIndex=-1;article.append(node("p",`${story.companies.join(" · ")} · ${story.publisher}`,"news-kicker"),node("h3",story.title),node("p",story.description,"news-description"));
 article.append(node("p",story.topics.join(" · "),"news-topics"));
 const status=node("p",story.review_status==="owner_approved"?"Buscable hoy · índice aprobado del chat":"No buscable en producción · espera aprobación del paquete",`news-status ${story.review_status}`);article.append(status);
 const dl=node("dl","");
 for(const [label,value] of [["Publicación",story.published_at],["Fecha del hecho",story.event_date?`${story.event_date}${story.event_end_date?` a ${story.event_end_date}`:""}`:"No documentada"],["Primera captura",story.first_captured_at??"No documentada en el índice histórico"]])dl.append(node("dt",label!),node("dd",value!));
 article.append(dl);
 const details=node("details","");details.append(node("summary","Fuentes y trazabilidad"));
 for(const source of story.sources){const href=safeSourceUrl(source.url);if(!href)continue;const publisher=source.publisher??(story.sources.length===1?story.publisher:"editor no documentado");const a=node("a",`Abrir fuente · ${publisher}`);a.href=href;a.target="_blank";a.rel="noopener noreferrer";details.append(a,node("p",`SHA-256: ${source.sha256}`,"news-hash"));}
 article.append(details);return article;
}
export function mountNews(root:string):Promise<void> {
 if(!pending)pending=loadNews(root);return pending;
}
async function loadNews(root:string):Promise<void> {
 const status=document.getElementById("news-coverage")!;
 try {
  const response=await fetch(`${root}/news.json`);if(!response.ok)throw Error("No disponible");
  const data=await response.json() as NewsArchive;
  archive=data;
  status.textContent=data.coverage_note;
  const eligibility=node("div","","news-chat-eligibility");
  const available=data.records.filter(r=>r.review_status==="owner_approved").length;
  eligibility.append(node("p",`Chat aprobado: ${available} fichas buscables hoy. Las ${data.records.length-available} candidatas esperan una sola decisión sobre el paquete; no están activadas en producción.`));
  const eligibleButton=node("button",`Ver las ${available} fichas buscables`);eligibleButton.type="button";eligibility.append(eligibleButton);status.after(eligibility);
  const month=document.getElementById("news-month") as HTMLSelectElement;
  const company=document.getElementById("news-company") as HTMLSelectElement;
  const topic=document.getElementById("news-topic") as HTMLSelectElement;
  const query=document.getElementById("news-query") as HTMLInputElement;
  const stateFilter=document.createElement("select");stateFilter.id="news-review-status";stateFilter.setAttribute("aria-label","Disponibilidad en el chat");stateFilter.append(new Option("Todas las fichas",""),new Option("Buscables hoy","owner_approved"),new Option("Pendientes del paquete","candidate_unapproved"));query.closest(".news-filters")?.append(stateFilter);
  let focusedIds:Set<string>|undefined;
  month.replaceChildren(new Option("Todos los meses",""),...data.months.map(m=>new Option(m,m)));month.value=(data.default_month && data.months.includes(data.default_month) ? data.default_month : data.months[0])??"";
  const topics=[...new Set(data.records.flatMap(r=>r.topics))].sort();topic.replaceChildren(new Option("Todos los temas",""),...topics.map(t=>new Option(t,t)));
  document.getElementById("news-limits")!.textContent=data.limits.join(" ");
  const grid=document.getElementById("news-stories")!;
  const resetFocus=node("button","Volver a todas las fichas");resetFocus.type="button";resetFocus.hidden=true;grid.before(resetFocus);
  function render(){const stories=filterStories(data.records,month.value,company.value,topic.value,query.value).filter(r=>(!stateFilter.value||r.review_status===stateFilter.value)&&(!focusedIds||focusedIds.has(r.id)));
   grid.replaceChildren(...stories.map(card));
   const approved=stories.filter(s=>s.review_status==="owner_approved").length;
   document.getElementById("news-count")!.textContent=`${stories.length} historias · ${approved} aprobadas · ${stories.length-approved} candidatas. Orden: publicación más reciente. La cantidad no mide importancia.`;
   if(!stories.length) grid.append(node("p","Sin fichas para estos filtros en el archivo parcial. No permite concluir que no ocurrieron noticias.","news-empty"));
   window.dispatchEvent(new CustomEvent("news-filter-changed"));
  }
  const changed=()=>{focusedIds=undefined;resetFocus.hidden=true;render();};
  for(const select of [month,company,topic,stateFilter])select.addEventListener("change",changed);query.addEventListener("input",changed);render();
  resetFocus.addEventListener("click",changed);
  eligibleButton.addEventListener("click",()=>{month.value="";company.value="";topic.value="";query.value="";stateFilter.value="owner_approved";changed();});
  selectResult=ids=>{const story=ids.length===1?data.records.find(r=>r.id===ids[0]):undefined;month.value=story?.published_at.slice(0,7)??"";company.value=story?.companies.length===1?story.companies[0]!:"";topic.value="";query.value="";stateFilter.value="";focusedIds=new Set(ids);resetFocus.hidden=false;render();};
  if(data.approval_package){const packageBox=node("details","");packageBox.append(node("summary","Revisar y aprobar juntas las once candidatas"));packageBox.append(node("p","La decisión puede referirse al paquete completo y su hash. No se activa ninguna ficha desde esta preview."));
   const download=node("button","Descargar paquete de aprobación");download.type="button";download.addEventListener("click",()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(data.approval_package,null,2)],{type:"application/json"}));const a=document.createElement("a");a.href=url;a.download="noticias-paquete-aprobacion-20261015.json";a.click();URL.revokeObjectURL(url);});packageBox.append(download);eligibility.append(packageBox);}
  const ask=document.getElementById("news-chat") as HTMLButtonElement;
  ask.hidden=import.meta.env.VITE_CHAT_ENABLED!=="true";
  ask.addEventListener("click",()=>{const entity=company.value||"las aerolíneas mexicanas";
   const text=`Busca noticias aprobadas sobre ${query.value||topic.value||"estrategia"} de ${entity}${month.value?` publicadas en ${month.value}`:""}. Cita las fuentes y distingue fecha de publicación y del hecho. Indica si no hay cobertura aprobada.`;
   window.dispatchEvent(new CustomEvent("airline-chat-prompt",{detail:{text,opener:ask}}));});
 }catch {status.textContent="El archivo mensual no está incluido en este build. La cobertura del chat conserva su índice aprobado.";pending=null;archive=null;}
}

export async function openNewsResult(result:NewsNavigation,item:NewsNavigationItem):Promise<boolean>{
 if(!archive||!selectResult)return false;
 const approved=result.corpus==="approved_only"&&result.index_sha256===archive.approved_index_sha256;
 const simulation=import.meta.env.VITE_NEWS_CANDIDATE_PREVIEW==="true"&&result.corpus==="candidate_simulation"&&result.index_sha256===archive.candidate_sha256;
 if(!approved&&!simulation)return false;
 const story=archive.records.find(r=>r.id===item.id&&r.story_id===item.story_id&&r.title===item.title&&r.published_at===item.published_at&&(simulation||r.review_status==="owner_approved")&&r.sources.some(s=>s.url===item.source_url&&s.sha256===item.source_sha256&&(s.publisher??r.publisher)===item.publisher));
 if(!story)return false;
 document.getElementById("tab-news")?.click();selectResult([story.id]);
 requestAnimationFrame(()=>{const card=document.getElementById(`news-story-${story.id}`);card?.scrollIntoView({block:"center"});card?.focus();});return true;
}

export async function openNewsMatches(result:NewsNavigation):Promise<boolean>{
 if(!archive||!selectResult)return false;
 const approved=result.corpus==="approved_only"&&result.index_sha256===archive.approved_index_sha256;
 const simulation=import.meta.env.VITE_NEWS_CANDIDATE_PREVIEW==="true"&&result.corpus==="candidate_simulation"&&result.index_sha256===archive.candidate_sha256;
 const ids=result.matching_ids;
 if((!approved&&!simulation)||!ids?.length||ids.length>50||new Set(ids).size!==ids.length||ids.some(id=>!archive!.records.some(r=>r.id===id&&(simulation||r.review_status==="owner_approved"))))return false;
 document.getElementById("tab-news")?.click();selectResult(ids);return true;
}
