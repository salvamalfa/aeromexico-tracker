export interface UnifiedTooltipRow { label: string; value: string; change?: string; color?: string; }
export interface UnifiedTooltipModel { heading: string; comparisonLabel: string; rows: UnifiedTooltipRow[]; }
type Provider = (key: string, index: number) => UnifiedTooltipModel | null;
interface Binding { keys: string[]; provider: Provider; index: number; hide: () => void; }
const bindings = new WeakMap<HTMLElement, Binding>();

// Shared rich point detail for mouse, touch and keyboard. A single date and
// comparison-period header serves every row; content is always text-safe.
export function bindUnifiedTooltip(graphId: string, keys: string[], provider: Provider): void {
  const graph = document.getElementById(graphId);
  if (!graph) return;
  const panelId = `${graphId}-detail`;
  const descriptions = new Set((graph.getAttribute("aria-describedby") ?? "").split(/\s+/).filter(Boolean));
  descriptions.add(panelId); graph.setAttribute("aria-describedby",[...descriptions].join(" "));
  const existing = bindings.get(graph);
  if (existing) { existing.keys = keys; existing.provider = provider; existing.hide(); return; }
  const panel = document.createElement("aside"); panel.className = "unified-tooltip"; panel.id = `${graphId}-detail`;
  panel.hidden = true; panel.setAttribute("role","status"); panel.setAttribute("aria-live","polite");
  panel.setAttribute("popover","manual"); document.body.append(panel);
  graph.tabIndex = 0;
  graph.setAttribute("aria-description","Toca un punto o usa las flechas izquierda y derecha para consultar los datos; Escape cierra el detalle.");
  let pinned = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const hide = () => {
    if(panel.dataset.topLayerOpen) panel.hidePopover?.();
    delete panel.dataset.topLayerOpen;panel.hidden = true;pinned = false;if(timer)clearTimeout(timer);
  };
  const binding: Binding = {keys,provider,index:keys.length-1,hide}; bindings.set(graph,binding);
  const show = (index: number, event?: MouseEvent) => {
    if (index < 0 || index >= binding.keys.length) return;
    binding.index = index;
    const model = binding.provider(binding.keys[index]!,index); if(!model) return;
    const header = document.createElement("header"), heading = document.createElement("b"), comparison = document.createElement("small");
    heading.textContent = model.heading; comparison.textContent = model.comparisonLabel; header.append(heading,comparison);
    const close = document.createElement("button"); close.type="button";close.className="unified-tooltip-close";close.textContent="×";close.setAttribute("aria-label","Cerrar detalle de datos");close.onclick=hide;
    const rows=model.rows.map(row=>{
      const line=document.createElement("p"), value=document.createElement("span"), change=document.createElement("span");
      value.textContent=`${row.label} ${row.value}`;change.textContent=row.change??"";
      if(row.color) change.style.color=row.color;line.append(value,change);return line;
    });
    panel.replaceChildren(close,header,...rows);panel.hidden=false;
    if(panel.showPopover&&!panel.dataset.topLayerOpen){panel.showPopover();panel.dataset.topLayerOpen="true";}
    const width=document.documentElement.clientWidth||window.innerWidth;
    const height=document.documentElement.clientHeight||window.innerHeight;
    panel.style.maxWidth=`${Math.max(0,width-16)}px`;
    const rect=graph.getBoundingClientRect(), box=panel.getBoundingClientRect();
    panel.style.left=`${Math.max(8,Math.min(event?.clientX??rect.left+12,width-box.width-8))}px`;
    panel.style.top=`${Math.max(8,Math.min((event?.clientY??rect.top+12)+12,height-box.height-8))}px`;
  };
  const unhover=()=>{if(timer)clearTimeout(timer);timer=setTimeout(()=>{if(!pinned&&!panel.contains(document.activeElement))hide();},180);};
  type PlotEvent={points?:Array<{x?:unknown;pointNumber?:number}>;event?:MouseEvent};
  const indexFrom=(event:PlotEvent)=>{
    const point=event.points?.[0];if(!point)return -1;
    const index=binding.keys.indexOf(String(point.x));return index>=0?index:point.pointNumber??-1;
  };
  const plot=graph as HTMLElement&{on?:(name:string,handler:(event:PlotEvent)=>void)=>void};
  plot.on?.("plotly_hover",event=>{if(timer)clearTimeout(timer);show(indexFrom(event),event.event);});
  plot.on?.("plotly_click",event=>{show(indexFrom(event),event.event);pinned=true;});
  plot.on?.("plotly_unhover",unhover);
  graph.addEventListener("focus",()=>show(binding.keys.length-1));
  graph.addEventListener("keydown",event=>{
    if(event.key==="Escape"){
      if(!panel.hidden){event.preventDefault();event.stopPropagation();hide();}return;
    }
    if(event.key!=="ArrowLeft"&&event.key!=="ArrowRight")return;
    event.preventDefault();pinned=true;show(Math.max(0,Math.min(binding.keys.length-1,binding.index+(event.key==="ArrowRight"?1:-1))));
  });
  graph.addEventListener("pointerleave",unhover);panel.addEventListener("pointerenter",()=>{if(timer)clearTimeout(timer);});panel.addEventListener("pointerleave",unhover);
  document.addEventListener("pointerdown",event=>{if(!panel.contains(event.target as Node)&&!graph.contains(event.target as Node))hide();});
  panel.addEventListener("keydown",event=>{if(event.key==="Escape"){event.preventDefault();event.stopPropagation();hide();}});
  window.addEventListener("reader-tab-visible",hide);
  window.addEventListener("resize",hide);
}

export const TOOLTIP_UP = "#165db5";
export const TOOLTIP_DOWN = "#c62828";
