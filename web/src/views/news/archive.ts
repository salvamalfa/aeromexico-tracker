export interface NewsStory {
 id:string; story_id:string; title:string; description:string; companies:string[]; topics:string[]; publisher:string;
 published_at:string; event_date:string|null; event_end_date:string|null; first_captured_at:string|null;
 review_status:"owner_approved"|"candidate_unapproved"; sources:{id:string;url:string;sha256:string;publisher?:string}[];
}
export interface NewsArchive {mode:string; approved_index_sha256?:string;candidate_sha256?:string|null;approval_package?:Record<string,unknown>|null; default_month?:string|null; coverage_note:string; months:string[]; records:NewsStory[]; limits:string[];}
export function filterStories(records:NewsStory[], month:string, company:string, topic:string, query:string):NewsStory[]{
 const norm=(x:string)=>x.normalize("NFD").replace(/[\u0300-\u036f]/g,"").toLowerCase();
 const tokens=norm(query).split(/\s+/).filter(Boolean);
 return records.filter(r=>(!month||r.published_at.startsWith(month))&&(!company||r.companies.includes(company))&&(!topic||r.topics.includes(topic))&&tokens.every(t=>norm([r.title,r.description,...r.companies,...r.topics].join(" ")).includes(t)));
}
export function safeSourceUrl(value:string):string|null {
 try{const url=new URL(value);return url.protocol==="https:"&&!url.username&&!url.password?url.href:null;}catch{return null;}
}
