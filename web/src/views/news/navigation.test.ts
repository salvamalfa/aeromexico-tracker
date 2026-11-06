import {beforeEach,expect,test,vi} from "vitest";
import {safeNewsResults} from "../chat/news-results";
import {readFileSync} from "node:fs";
import {resolve} from "node:path";
import {quarterForPublicationDate,storiesForQuarter,type NewsArchive} from "./archive";
const period=vi.hoisted(()=>({selected:"2026Q2" as string|null,listeners:[] as ((id:string)=>void)[]}));
vi.mock("../../state/period",()=>({currentPeriodId:()=>period.selected,subscribe:(listener:(id:string)=>void)=>period.listeners.push(listener)}));
const item={id:"known",story_id:"known",title:"Noticia conocida",published_at:"2026-04-30",publisher:"FlightGlobal",source_url:"https://www.flightglobal.com/known",source_sha256:"b".repeat(64)};
const result={corpus:"approved_only" as const,index_sha256:"a".repeat(64),filters:{},total:1,items:[item]};
function story(id:string,published_at:string){return {...item,id,story_id:id,published_at,title:`Historia ${id}`};}
beforeEach(()=>{vi.resetModules();period.selected=new URLSearchParams(window.location.search).get("period")??"2026Q2";period.listeners=[];document.body.innerHTML='<button id="tab-news"></button><section id="panel-news" hidden><span id="news-source"></span><div class="news-filters"><select id="news-month"></select><select id="news-company"><option value=""></option></select><select id="news-topic"></select><input id="news-query"></div><p id="news-count"></p><div id="news-stories"></div><button id="news-chat"></button></section>';const base={...item,description:"Resumen original",companies:[],topics:[],review_status:"owner_approved",sources:[{id:"source",url:item.source_url,sha256:item.source_sha256}]};vi.stubGlobal("fetch",vi.fn().mockResolvedValue({ok:true,json:async()=>({mode:"approved_only",approved_index_sha256:"a".repeat(64),coverage_note:"Parcial",months:["2026-04","2026-09","2026-10"],limits:[],records:[{...base},...[["q3","2026-09-30"],["q4","2026-10-01"]].map(([id,date])=>({...base,...story(id!,date!)}))]})}));vi.stubGlobal("requestAnimationFrame",(fn:()=>void)=>{fn();return 1;});Element.prototype.scrollIntoView=vi.fn();});
test("unknown ids, altered citations and candidate mode cannot navigate",async()=>{
 const news=await import("./bootstrap");await news.mountNews("data/v1");const clicked=vi.fn();document.getElementById("tab-news")!.addEventListener("click",clicked);
 expect(await news.openNewsResult(result,{...item,id:"invented"})).toBe(false);
 expect(await news.openNewsResult(result,{...item,source_sha256:"c".repeat(64)})).toBe(false);
 expect(await news.openNewsResult({...result,corpus:"candidate_simulation"},item)).toBe(false);
 expect(clicked).not.toHaveBeenCalled();
 expect(await news.openNewsResult(result,item)).toBe(true);expect(clicked).toHaveBeenCalledOnce();
 expect(document.querySelector<HTMLElement>(".news-card")!.dataset.newsId).toBe("known");
});
test("unsafe source URLs and invented corpus fingerprints do not render actionable results",()=>{
 expect(safeNewsResults([{...result,items:[{...item,source_url:"javascript:alert(1)"}]}])).toEqual([]);
 expect(safeNewsResults([{...result,items:[{...item,source_url:"https://user:secret@www.flightglobal.com/a"}]}])).toEqual([]);
 expect(safeNewsResults([{...result,index_sha256:"invented"}])).toEqual([]);
});
test("bulk navigation fails closed for invented or candidate identifiers",async()=>{
 const news=await import("./bootstrap");await news.mountNews("data/v1");
 expect(await news.openNewsMatches({...result,matching_ids:["known","invented"],total:2})).toBe(false);
 expect(await news.openNewsMatches({...result,matching_ids:["known","known"],total:2})).toBe(false);
 expect(await news.openNewsMatches({...result,matching_ids:["known"]})).toBe(true);
 expect(document.querySelectorAll(".news-card")).toHaveLength(1);
});
test("selected quarter follows the shared period and preserves out-of-quarter stories with dates",async()=>{
 document.querySelector(".news-filters")?.remove();document.getElementById("news-chat")?.remove();
 const news=await import("./bootstrap");await news.mountNews("data/v1");
 expect(document.querySelectorAll("#news-stories .news-card")).toHaveLength(1);
 expect(document.querySelector("#news-stories .news-date")?.textContent).toBe("Publicada: 2026-04-30");
 expect(document.getElementById("news-coverage")).toBeNull();
 expect(document.getElementById("news-count")).toHaveProperty("hidden",true);
 expect(document.getElementById("news-count")?.textContent).toBe("");
 const summary=document.querySelector<HTMLElement>("#news-outside summary")!;
 expect(summary.textContent).toBe("Ver todas");
 summary.click();
 expect(document.querySelectorAll("#news-outside-stories .news-card")).toHaveLength(2);
 period.selected="2026Q3";period.listeners.forEach(listener=>listener("2026Q3"));
 expect(document.querySelectorAll("#news-stories .news-card")).toHaveLength(1);
 expect(document.querySelector("#news-stories .news-date")?.textContent).toBe("Publicada: 2026-09-30");
 expect(summary.textContent).toBe("Ver todas");
 expect([...document.querySelectorAll("#news-outside-stories .news-date")].map(el=>el.textContent))
  .toEqual(["Publicada: 2026-04-30","Publicada: 2026-10-01"]);
 period.selected="2026Q2";period.listeners.forEach(listener=>listener("2026Q2"));
 expect(document.querySelectorAll("#news-stories .news-card")).toHaveLength(1);
 expect(document.querySelector<HTMLElement>("#news-stories .news-card")?.dataset.newsId).toBe("known");
 expect(summary.textContent).toBe("Ver todas");
});

test("direct quarter links initialize the news view from the dashboard period",async()=>{
 window.history.replaceState(null,"","/?period=2026Q3");period.selected=new URLSearchParams(window.location.search).get("period");
 const news=await import("./bootstrap");await news.mountNews("data/v1");
 expect(document.querySelectorAll("#news-stories .news-card")).toHaveLength(1);
 expect(document.querySelector("#news-stories .news-date")?.textContent).toBe("Publicada: 2026-09-30");
 expect(document.querySelector("#news-outside summary")?.textContent).toBe("Ver todas");
});

test("real approved archive maps only published dates to quarters and retains all October notes outside Q3",()=>{
 const archive=JSON.parse(readFileSync(resolve(process.cwd(),"../site/data/v1/news.json"),"utf8")) as NewsArchive;
 const q2=storiesForQuarter(archive.records,"2026Q2");
 const q3=storiesForQuarter(archive.records,"2026Q3");
 expect(q2.selected).toHaveLength(1);
 expect(q3.selected).toHaveLength(16);
 expect(q3.outside).toHaveLength(10);
 expect(q3.outside.filter(story=>story.published_at.startsWith("2026-10"))).toHaveLength(9);
});

test("invalid publication dates are not assigned to a quarter",()=>{
 expect(quarterForPublicationDate("2026-02-30")).toBeNull();
 expect(quarterForPublicationDate("2026-13-01")).toBeNull();
 expect(quarterForPublicationDate("unknown")).toBeNull();
});

test("real archive UI shows Q3 and keeps October visible in the dated outside-period list",async()=>{
 const archive=JSON.parse(readFileSync(resolve(process.cwd(),"../site/data/v1/news.json"),"utf8")) as NewsArchive;
 vi.stubGlobal("fetch",vi.fn().mockResolvedValue({ok:true,json:async()=>archive}));
 period.selected="2026Q3";
 const news=await import("./bootstrap");await news.mountNews("data/v1");
 expect(document.querySelectorAll("#news-stories .news-card")).toHaveLength(16);
 const summary=document.querySelector<HTMLElement>("#news-outside summary")!;
 expect(summary.textContent).toBe("Ver todas");
 expect(summary.parentElement?.previousElementSibling?.id).toBe("news-stories");
 expect(summary.parentElement).toHaveProperty("open",false);
 summary.click();
 expect(summary.parentElement).toHaveProperty("open",true);
 const outsideDates=[...document.querySelectorAll("#news-outside-stories .news-date")].map(el=>el.textContent);
 expect(outsideDates).toHaveLength(10);
 expect(outsideDates.filter(date=>date?.includes("2026-10"))).toHaveLength(9);
});
test("secondary source target opens the primary story card with its verified citation",async()=>{
 const response=await fetch("");const payload=await response.json();
 const secondary={id:"secondary",url:"https://www.flightglobal.com/secondary",sha256:"c".repeat(64),publisher:"Otro editor"};
 payload.records[0].sources.push(secondary);
 vi.stubGlobal("fetch",vi.fn().mockResolvedValue({ok:true,json:async()=>payload}));
 const news=await import("./bootstrap");await news.mountNews("data/v1");
 expect(await news.openNewsResult(result,{...item,publisher:secondary.publisher,source_url:secondary.url,source_sha256:secondary.sha256})).toBe(true);
 expect(document.querySelectorAll(".news-card")).toHaveLength(1);
 expect(document.querySelectorAll(".news-card a")).toHaveLength(2);
});

test("archive heading has one contextual question action without an extra filter block",async()=>{
 document.body.innerHTML='<main class="page-shell"><div id="news-heading" class="section-heading news-heading"><h2>Archivo mensual</h2></div><p id="news-count"></p><div id="news-stories"></div></main>';
 const news=await import("./bootstrap");await news.mountNews("data/v1");
 const {mountChatCardActions}=await import("../chat/card-actions");const open=vi.fn();const dispose=mountChatCardActions(open);
 const action=document.querySelector<HTMLButtonElement>("#news-heading > .chat-card-action")!;
 expect(action.textContent).toBe("Pregunta");expect(action.getAttribute("aria-label")).toBe("Preguntar sobre Archivo mensual");
 expect(document.querySelector(".news-filters")).toBeNull();expect(document.querySelector("#news-review-status")).toBeNull();
 action.click();expect(open).toHaveBeenCalledWith(document.getElementById("news-heading"),action);dispose();
});
