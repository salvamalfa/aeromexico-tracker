import {beforeEach,expect,test,vi} from "vitest";
import {safeNewsResults} from "../chat/news-results";
const item={id:"known",story_id:"known",title:"Noticia conocida",published_at:"2026-04-30",publisher:"FlightGlobal",source_url:"https://www.flightglobal.com/known",source_sha256:"b".repeat(64)};
const result={corpus:"approved_only" as const,index_sha256:"a".repeat(64),filters:{},total:1,items:[item]};
beforeEach(()=>{vi.resetModules();document.body.innerHTML='<button id="tab-news"></button><section id="panel-news" hidden><span id="news-source"></span><div class="news-filters"><select id="news-month"></select><select id="news-company"><option value=""></option></select><select id="news-topic"></select><input id="news-query"></div><p id="news-count"></p><div id="news-stories"></div><button id="news-chat"></button></section>';vi.stubGlobal("fetch",vi.fn().mockResolvedValue({ok:true,json:async()=>({mode:"approved_only",approved_index_sha256:"a".repeat(64),coverage_note:"Parcial",months:["2026-04"],limits:[],records:[{...item,description:"Resumen original",companies:[],topics:[],review_status:"owner_approved",sources:[{id:"source",url:item.source_url,sha256:item.source_sha256}]}]})}));vi.stubGlobal("requestAnimationFrame",(fn:()=>void)=>{fn();return 1;});Element.prototype.scrollIntoView=vi.fn();});
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
test("news chat button sends selected filters without searchable instruction boilerplate",async()=>{
 const news=await import("./bootstrap");await news.mountNews("data/v1");
 const received=vi.fn();window.addEventListener("airline-chat-prompt",received,{once:true});
 (document.getElementById("news-query") as HTMLInputElement).value="unicornios";
 document.getElementById("news-chat")!.click();
 expect(received.mock.calls[0]![0].detail.text).toBe("Busca noticias publicadas en 2026-04 sobre unicornios.");
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
