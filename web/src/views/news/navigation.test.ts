import {beforeEach,expect,test,vi} from "vitest";
import {safeNewsResults} from "../chat/news-results";
const item={id:"known",story_id:"known",title:"Noticia conocida",published_at:"2026-04-30",publisher:"FlightGlobal",source_url:"https://www.flightglobal.com/known",source_sha256:"b".repeat(64)};
const result={corpus:"approved_only" as const,index_sha256:"a".repeat(64),filters:{},total:1,items:[item]};
beforeEach(()=>{vi.resetModules();document.body.innerHTML='<button id="tab-news"></button><section id="panel-news" hidden><p id="news-coverage"></p><div class="news-filters"><select id="news-month"></select><select id="news-company"><option value=""></option></select><select id="news-topic"></select><input id="news-query"></div><p id="news-limits"></p><p id="news-count"></p><div id="news-stories"></div><button id="news-chat"></button></section>';vi.stubGlobal("fetch",vi.fn().mockResolvedValue({ok:true,json:async()=>({mode:"approved_only",approved_index_sha256:"a".repeat(64),coverage_note:"Parcial",months:["2026-04"],limits:[],records:[{...item,description:"Resumen original",companies:[],topics:[],review_status:"owner_approved",sources:[{id:"source",url:item.source_url,sha256:item.source_sha256}]}]})}));vi.stubGlobal("requestAnimationFrame",(fn:()=>void)=>{fn();return 1;});Element.prototype.scrollIntoView=vi.fn();});
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
