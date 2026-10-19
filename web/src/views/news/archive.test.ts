import { describe,it,expect } from "vitest";
import { filterStories,safeSourceUrl,type NewsStory } from "./archive";
const story={id:"1",title:"Viva ajusta capacidad",description:"Tráfico de septiembre",companies:["Viva"],topics:["capacidad"],published_at:"2026-10-09"} as NewsStory;
describe("bounded archive filters",()=>{
 it("uses publication month, normalizes accents and combines all filters",()=>{expect(filterStories([story],"2026-10","Viva","capacidad","trafico septiembre")).toEqual([story]);expect(filterStories([story],"2026-09","","","")).toEqual([]);expect(filterStories([story],"","Volaris","","")).toEqual([]);});
 it("rejects unsafe source protocols and credential URLs",()=>{expect(safeSourceUrl("javascript:alert(1)")).toBeNull();expect(safeSourceUrl("https://user:password@host.example")).toBeNull();expect(safeSourceUrl("https://ri.vivaaerobus.com/doc")).toContain("https:");});
});

it("keeps Connect and its parent separate when filtering supported cards",()=>{
 const parent={...story,id:"parent",companies:["Aeroméxico"]};
 const connect={...story,id:"connect",companies:["Aeroméxico Connect"]};
 expect(filterStories([parent,connect],"","Aeroméxico Connect","","")).toEqual([connect]);
 expect(filterStories([parent,connect],"","Aeroméxico","","")).toEqual([parent]);
});
