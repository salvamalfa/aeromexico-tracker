import { expect,it } from "vitest";
import { mountChatPrompt } from "./prompt";
it("prefills through the existing input without submitting and removes its listener",()=>{
 const input=document.createElement("textarea");let opened=0;let changed=0;input.addEventListener("input",()=>changed++);
 const dispose=mountChatPrompt(input,()=>opened++);
 const fire=(text:string)=>window.dispatchEvent(new CustomEvent("airline-chat-prompt",{detail:{text}}));
 fire("Busca noticias aprobadas de Viva");expect(input.value).toContain("Viva");expect(opened).toBe(1);expect(changed).toBe(1);
 input.disabled=true;fire("No debe reemplazar un turno activo");expect(opened).toBe(1);
 dispose();input.disabled=false;fire("Ya desmontado");expect(opened).toBe(1);
});
