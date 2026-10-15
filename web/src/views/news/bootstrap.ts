import { filterStories, safeSourceUrl, type NewsArchive, type NewsStory } from "./archive";
import "./news.css";
let mounted=false;
function node<K extends keyof HTMLElementTagNameMap>(tag:K,text:string,className="") { const el=document.createElement(tag);el.textContent=text;el.className=className;return el; }
function card(story:NewsStory) {
 const article=node("article","","news-card");article.append(node("p",`${story.companies.join(" · ")} · ${story.publisher}`,"news-kicker"),node("h3",story.title),node("p",story.description,"news-description"));
 article.append(node("p",story.topics.join(" · "),"news-topics"));
 const status=node("p",story.review_status==="owner_approved"?"Aprobada para evidencia del chat":"Candidata · pendiente de aprobación",`news-status ${story.review_status}`);article.append(status);
 const dl=node("dl","");
 for(const [label,value] of [["Publicación",story.published_at],["Fecha del hecho",story.event_date?`${story.event_date}${story.event_end_date?` a ${story.event_end_date}`:""}`:"No documentada"],["Primera captura",story.first_captured_at??"No documentada en el índice histórico"]])dl.append(node("dt",label!),node("dd",value!));
 article.append(dl);
 const details=node("details","");details.append(node("summary","Fuentes y trazabilidad"));
 for(const source of story.sources){const href=safeSourceUrl(source.url);if(!href)continue;const a=node("a",`Abrir fuente · ${story.publisher}`);a.href=href;a.target="_blank";a.rel="noopener noreferrer";details.append(a,node("p",`SHA-256: ${source.sha256}`,"news-hash"));}
 article.append(details);return article;
}
export async function mountNews(root:string):Promise<void> {
 if(mounted)return;mounted=true;
 const status=document.getElementById("news-coverage")!;
 try {
  const response=await fetch(`${root}/news.json`);if(!response.ok)throw Error("No disponible");
  const data=await response.json() as NewsArchive;
  status.textContent=data.coverage_note;
  const month=document.getElementById("news-month") as HTMLSelectElement;
  const company=document.getElementById("news-company") as HTMLSelectElement;
  const topic=document.getElementById("news-topic") as HTMLSelectElement;
  const query=document.getElementById("news-query") as HTMLInputElement;
  month.replaceChildren(new Option("Todos los meses",""),...data.months.map(m=>new Option(m,m)));month.value=(data.default_month && data.months.includes(data.default_month) ? data.default_month : data.months[0])??"";
  const topics=[...new Set(data.records.flatMap(r=>r.topics))].sort();topic.replaceChildren(new Option("Todos los temas",""),...topics.map(t=>new Option(t,t)));
  document.getElementById("news-limits")!.textContent=data.limits.join(" ");
  const grid=document.getElementById("news-stories")!;
  function render(){const stories=filterStories(data.records,month.value,company.value,topic.value,query.value);
   grid.replaceChildren(...stories.map(card));
   const approved=stories.filter(s=>s.review_status==="owner_approved").length;
   document.getElementById("news-count")!.textContent=`${stories.length} historias · ${approved} aprobadas · ${stories.length-approved} candidatas. Orden: publicación más reciente. La cantidad no mide importancia.`;
   if(!stories.length) grid.append(node("p","Sin fichas para estos filtros en el archivo parcial. No permite concluir que no ocurrieron noticias.","news-empty"));
   window.dispatchEvent(new CustomEvent("news-filter-changed"));
  }
  for(const select of [month,company,topic])select.addEventListener("change",render);query.addEventListener("input",render);render();
  const ask=document.getElementById("news-chat") as HTMLButtonElement;
  ask.hidden=import.meta.env.VITE_CHAT_ENABLED!=="true";
  ask.addEventListener("click",()=>{const entity=company.value||"las aerolíneas mexicanas";
   const text=`Busca noticias aprobadas sobre ${query.value||topic.value||"estrategia"} de ${entity}${month.value?` publicadas en ${month.value}`:""}. Cita las fuentes y distingue fecha de publicación y del hecho. Indica si no hay cobertura aprobada.`;
   window.dispatchEvent(new CustomEvent("airline-chat-prompt",{detail:{text,opener:ask}}));});
 }catch {status.textContent="El archivo mensual no está incluido en este build. La cobertura del chat conserva su índice aprobado.";mounted=false;}
}
