import { expect,it } from "vitest";
import { mountChatCardActions } from "./card-actions";
it("does not advertise a chat tool for an unsupported dataset",()=>{
 document.body.innerHTML='<main class="page-shell"><article class="chart-card" id="supported"></article><article class="chart-card" id="airport" data-chat-unavailable></article></main>';
 const dispose=mountChatCardActions(()=>{},()=>{});
 expect(document.querySelectorAll("#supported .chat-card-action")).toHaveLength(1);
 expect(document.querySelectorAll("#airport .chat-card-action")).toHaveLength(0);
 dispose();
});
