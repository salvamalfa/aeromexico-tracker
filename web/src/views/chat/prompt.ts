// Public UI shortcut: prefill only, retaining the existing submission and auth flow.
import { MAX_INPUT } from "./template";
export function mountChatPrompt(input:HTMLTextAreaElement,open:(opener?:HTMLElement)=>void):()=>void {
 const onPrompt=(event:Event)=>{
  const detail=(event as CustomEvent<{text:string;opener?:HTMLElement}>).detail;
  if(!detail||typeof detail.text!=="string"||input.disabled)return;
  input.value=detail.text.slice(0,MAX_INPUT);input.dispatchEvent(new Event("input"));open(detail.opener);
 };
 window.addEventListener("airline-chat-prompt",onPrompt);
 return ()=>window.removeEventListener("airline-chat-prompt",onPrompt);
}
