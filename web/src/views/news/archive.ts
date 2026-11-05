export interface NewsStory {
 id:string; story_id:string; title:string; description:string; companies:string[]; topics:string[]; publisher:string;
 published_at:string; event_date:string|null; event_end_date:string|null; first_captured_at:string|null;
 review_status:"owner_approved"|"candidate_unapproved"; sources:{id:string;url:string;sha256:string;publisher?:string}[];
}
export interface NewsArchive {mode:string; approved_index_sha256?:string;candidate_sha256?:string|null;approval_package?:Record<string,unknown>|null; default_month?:string|null; coverage_note:string; months:string[]; records:NewsStory[]; limits:string[];}
export interface NewsQuarterStories { selected:NewsStory[]; outside:NewsStory[]; undated:NewsStory[]; }
export function quarterForPublicationDate(value:string):string|null {
 const match=/^(\d{4})-(\d{2})-\d{2}$/.exec(value);
 if(!match)return null;
 const year=Number(match[1]),month=Number(match[2]),day=Number(value.slice(-2));
 const date=new Date(Date.UTC(year,month-1,day));
 if(month<1||month>12||day<1||date.getUTCFullYear()!==year||date.getUTCMonth()!==month-1||date.getUTCDate()!==day)return null;
 return `${match[1]}Q${Math.ceil(month/3)}`;
}
export function storiesForQuarter(records:NewsStory[],periodId:string|null|undefined):NewsQuarterStories {
 if(!periodId)return {selected:records,outside:[],undated:[]};
 const selected:NewsStory[]=[],outside:NewsStory[]=[],undated:NewsStory[]=[];
 for(const story of records){
  const quarter=quarterForPublicationDate(story.published_at);
  if(!quarter)undated.push(story);
  else if(quarter===periodId)selected.push(story);
  else outside.push(story);
 }
 return {selected,outside,undated};
}
export function quarterLabel(periodId:string):string {
 const match=/^(\d{4})Q([1-4])$/.exec(periodId);
 return match?`${match[2]}T${match[1]!.slice(-2)}`:periodId;
}
export function filterStories(records:NewsStory[], month:string, company:string, topic:string, query:string):NewsStory[]{
 const norm=(x:string)=>x.normalize("NFD").replace(/[\u0300-\u036f]/g,"").toLowerCase();
 const tokens=norm(query).split(/\s+/).filter(Boolean);
 return records.filter(r=>(!month||r.published_at.startsWith(month))&&(!company||r.companies.includes(company))&&(!topic||r.topics.includes(topic))&&tokens.every(t=>norm([r.title,r.description,...r.companies,...r.topics].join(" ")).includes(t)));
}
export function safeSourceUrl(value:string):string|null {
 try{const url=new URL(value);return url.protocol==="https:"&&!url.username&&!url.password?url.href:null;}catch{return null;}
}
