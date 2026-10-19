import { state } from "../executive/state";

export interface NewsNavigationItem {id:string;story_id:string;title:string;published_at:string;publisher:string;source_url:string;source_sha256:string;}
export interface NewsNavigation {corpus:"approved_only"|"candidate_simulation";index_sha256:string;items:NewsNavigationItem[];total:number;filters:Record<string,unknown>;matching_ids?:string[];}
function safeUrl(raw:unknown):boolean{if(typeof raw!=="string"||raw.length>1000)return false;try{const u=new URL(raw);return u.protocol==="https:"&&!u.username&&!u.password;}catch{return false;}}
export function safeNewsResults(raw:unknown):NewsNavigation[] {
 if(!Array.isArray(raw)||raw.length>8)return [];
 return raw.flatMap(value=>{
  if(!value||typeof value!=="object")return [];
  const r=value as NewsNavigation;
  if(r.corpus!=="approved_only"&&!(import.meta.env.VITE_NEWS_CANDIDATE_PREVIEW==="true"&&r.corpus==="candidate_simulation"))return [];
  if(!/^[a-f0-9]{64}$/.test(r.index_sha256)||!Array.isArray(r.items)||r.items.length>5||!Number.isInteger(r.total)||r.total<r.items.length)return [];
  if(r.items.some(item=>!item||!/^[-A-Za-z0-9_.]{1,120}$/.test(item.id)||!/^[-A-Za-z0-9_.]{1,120}$/.test(item.story_id)||typeof item.title!=="string"||item.title.length>300||typeof item.publisher!=="string"||item.publisher.length>120||!/^\d{4}-\d{2}-\d{2}$/.test(item.published_at)||!safeUrl(item.source_url)||!/^[a-f0-9]{64}$/.test(item.source_sha256)))return [];
  const ids=r.matching_ids??r.items.map(item=>item.id);
  if(!Array.isArray(ids)||ids.length>50||new Set(ids).size!==ids.length||ids.some(id=>typeof id!=="string"||!/^[-A-Za-z0-9_.]{1,120}$/.test(id))||r.total<ids.length||r.items.some(item=>!ids.includes(item.id)))return [];
  return [{...r,matching_ids:ids}];
 });
}

export function renderNewsResults(raw:unknown):HTMLElement|undefined {
 const results=safeNewsResults(raw);if(!results.length)return;
 const root=document.createElement("section");root.className="chat-news-results";root.setAttribute("aria-label","Resultados de noticias");
 for(const result of results){
  const label=document.createElement("p");label.textContent=`${result.corpus==="approved_only"?"Índice aprobado":"Simulación candidata"}: ${result.items.length} de ${result.total} coincidencias resumidas. Hasta 50 fichas navegables por consulta.`;root.append(label);
  if(!result.items.length){const empty=document.createElement("p");empty.textContent="No hay coincidencias en este corpus. Esto no demuestra ausencia de noticias.";root.append(empty);}
  const ids=result.matching_ids??[];
  if(ids.length>1){const bulk=document.createElement("button");bulk.type="button";bulk.textContent=`Mostrar ${ids.length} de ${result.total} fichas en Noticias`;
   bulk.addEventListener("click",()=>{void import("../news/bootstrap").then(async news=>{await news.mountNews(state.dataRoot);if(await news.openNewsMatches(result)){document.querySelector<HTMLButtonElement>("[data-chat-close]")?.click();}else{label.textContent="Las referencias no corresponden al corpus visible. No se abrió ninguna ficha.";}});});root.append(bulk);}
  for(const item of result.items){const button=document.createElement("button");button.type="button";button.className="chat-news-open";button.textContent=`Ver ficha: ${item.title} · ${item.published_at}`;
   button.addEventListener("click",()=>{void import("../news/bootstrap").then(async news=>{await news.mountNews(state.dataRoot);if(await news.openNewsResult(result,item)){document.querySelector<HTMLButtonElement>("[data-chat-close]")?.click();}else{label.textContent="La referencia no pertenece al corpus visible o cambió de versión. No se abrió ninguna ficha.";}});});root.append(button);}
 }
 return root;
}
