import { quarterForPublicationDate, quarterLabel, safeSourceUrl, storiesForQuarter, type NewsArchive, type NewsStory } from "./archive";
import "./news.css";
import type { NewsNavigation, NewsNavigationItem } from "../chat/news-results";
import { currentPeriodId, subscribe } from "../../state/period";
let pending:Promise<void>|null=null;
let archive:NewsArchive|null=null;
let selectResult:((ids:string[])=>void)|null=null;
function node<K extends keyof HTMLElementTagNameMap>(tag:K,text:string,className="") { const el=document.createElement(tag);el.textContent=text;el.className=className;return el; }
function card(story:NewsStory) {
 const article=node("article","","news-card");article.id=`news-story-${story.id}`;article.dataset.newsId=story.id;article.tabIndex=-1;
 article.append(node("p",quarterForPublicationDate(story.published_at)?`Publicada: ${story.published_at}`:"Fecha de publicación no verificable","news-date"),node("h3",story.title),node("p",story.description,"news-description"));
 if(story.review_status==="candidate_unapproved")article.append(node("p","Pendiente de aprobación","news-status candidate_unapproved"));
 const sources=node("div","","news-sources");sources.append(node("span","Fuentes:","news-sources-label"));
 for(const source of story.sources){
  const href=safeSourceUrl(source.url);if(!href)continue;
  const publisher=source.publisher??story.publisher;
  const a=node("a",publisher);a.href=href;a.target="_blank";a.rel="noopener noreferrer";sources.append(a);
 }
 article.append(sources);return article;
}
export function mountNews(root:string):Promise<void> {
 if(!pending)pending=loadNews(root);return pending;
}
async function loadNews(root:string):Promise<void> {
 const status=document.getElementById("news-count")!;
 status.hidden=false;
 status.textContent="Cargando noticias…";
 try {
  const response=await fetch(`${root}/news.json`);if(!response.ok)throw Error("No disponible");
  const data=await response.json() as NewsArchive;
  archive=data;
  const grid=document.getElementById("news-stories")!;
  let periodId=currentPeriodId()??null;
  let focusedIds:Set<string>|undefined;
  const resetFocus=node("button","Volver a todas las noticias","news-reset");resetFocus.type="button";resetFocus.hidden=true;grid.before(resetFocus);
  const outside=document.createElement("details");outside.className="news-outside";outside.id="news-outside";
  outside.append(node("summary","Ver todas"));
  const outsideGrid=node("div","","news-grid");outsideGrid.id="news-outside-stories";outside.append(outsideGrid);grid.after(outside);
  function render(){
   const partition=storiesForQuarter(data.records,periodId);
   const stories=partition.selected.filter(r=>!focusedIds||focusedIds.has(r.id));
   const other=partition.outside.filter(r=>!focusedIds||focusedIds.has(r.id));
   const undated=partition.undated.filter(r=>!focusedIds||focusedIds.has(r.id));
   grid.replaceChildren(...stories.map(card));
   if(!stories.length)grid.append(node("p",`No hay noticias en el archivo para ${periodId?quarterLabel(periodId):"el periodo seleccionado"}.`,"news-empty"));
   outsideGrid.replaceChildren(...other.map(card));
   if(undated.length){
    const undatedGroup=node("section","","news-undated");undatedGroup.append(node("h3","Sin fecha de publicación verificable"),...undated.map(card));outsideGrid.append(undatedGroup);
   }
   outside.hidden=!other.length&&!undated.length;
   window.dispatchEvent(new CustomEvent("news-filter-changed"));
  }
  resetFocus.addEventListener("click",()=>{focusedIds=undefined;resetFocus.hidden=true;render();});
  selectResult=ids=>{focusedIds=new Set(ids);resetFocus.hidden=false;render();const partition=storiesForQuarter(data.records,periodId);const outsideIds=new Set([...partition.outside,...partition.undated].map(story=>story.id));outside.open=ids.some(id=>outsideIds.has(id));};
  subscribe(next=>{periodId=next;focusedIds=undefined;resetFocus.hidden=true;render();});
  render();
  status.textContent="";
  status.hidden=true;
 }catch {status.textContent="No se pudo cargar el archivo de noticias. Intenta de nuevo más tarde.";pending=null;archive=null;}
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
