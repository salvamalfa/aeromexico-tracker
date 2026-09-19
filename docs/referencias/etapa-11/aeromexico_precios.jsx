import { useState } from "react";
import {
  LineChart, Line, BarChart, Bar, ScatterChart, Scatter,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  ReferenceLine, Area, AreaChart, ComposedChart
} from "recharts";

// ─── Datos consolidados 1T21 – 4T25 ────────────────────────────────────────
const data = [
  // iask = Ingreso total / ASK (¢ USD)   yield_c = Yield (¢ USD, pasajero-km)
  // ip_ask = Ingreso pasaje / ASK (¢ USD) cask = Costo / ASK (¢ USD)
  // pax = Pasajeros (miles)               load = Factor de ocupación (%)
  { q:"1T21", iask:4.75, yield_c:5.25, ip_ask:3.58, cask:7.20, pax:3157, load:68.8 },
  { q:"2T21", iask:6.40, yield_c:7.03, ip_ask:5.36, cask:7.30, pax:3969, load:76.8 },
  { q:"3T21", iask:6.85, yield_c:7.38, ip_ask:5.78, cask:6.80, pax:4556, load:78.8 },
  { q:"4T21", iask:7.30, yield_c:7.80, ip_ask:6.20, cask:6.60, pax:4871, load:80.8 },
  { q:"1T22", iask:6.50, yield_c:7.00, ip_ask:5.20, cask:7.80, pax:4142, load:75.6 },
  { q:"2T22", iask:7.90, yield_c:7.70, ip_ask:6.30, cask:8.00, pax:5551, load:83.0 },
  { q:"3T22", iask:8.30, yield_c:7.90, ip_ask:6.60, cask:7.60, pax:5895, load:84.0 },
  { q:"4T22", iask:9.20, yield_c:9.30, ip_ask:7.50, cask:8.40, pax:6137, load:82.2 },
  { q:"1T23", iask:8.60, yield_c:8.20, ip_ask:6.50, cask:7.90, pax:5756, load:80.1 },
  { q:"2T23", iask:9.00, yield_c:8.80, ip_ask:7.30, cask:7.40, pax:6043, load:84.4 },
  { q:"3T23", iask:9.80, yield_c:9.30, ip_ask:8.10, cask:7.90, pax:6667, load:88.0 },
  { q:"4T23", iask:10.00,yield_c:null, ip_ask:8.20, cask:8.40, pax:6228, load:84.0 },
  { q:"1T24", iask:9.50, yield_c:null, ip_ask:null,  cask:8.00, pax:5979, load:85.4 },
  { q:"2T24", iask:9.70, yield_c:null, ip_ask:null,  cask:7.80, pax:6409, load:86.3 },
  { q:"3T24", iask:9.90, yield_c:null, ip_ask:null,  cask:7.60, pax:6703, load:88.9 },
  { q:"4T24", iask:10.00,yield_c:null, ip_ask:null,  cask:8.10, pax:6246, load:85.5 },
  { q:"1T25", iask:8.50, yield_c:null, ip_ask:null,  cask:7.40, pax:5877, load:82.3 },
  { q:"2T25", iask:9.00, yield_c:null, ip_ask:null,  cask:7.40, pax:6180, load:85.7 },
  { q:"3T25", iask:9.57, yield_c:null, ip_ask:null,  cask:7.89, pax:6362, load:88.3 },
  { q:"4T25", iask:10.19,yield_c:null, ip_ask:null,  cask:8.45, pax:6168, load:87.2 },
];

// Color palette (brand-inspired)
const AZUL  = "#003087";
const ROJO  = "#E31C23";
const GRIS  = "#6B7280";
const VERDE = "#059669";
const AMBER = "#D97706";

const yrs = ["2021","2022","2023","2024","2025"];
const bandColors = ["#EFF6FF","#FFF7ED","#F0FDF4","#FDF4FF","#FEFCE8"];

// Quarter label helper
const shortQ = (q) => q.replace("T","Q").slice(-2) === "Q1" ? q : q.slice(-2);

// ─── Custom Tooltip ──────────────────────────────────────────────────────────
const CustomTip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-lg p-3 text-xs">
      <p className="font-bold text-gray-800 mb-1">{label}</p>
      {payload.map((p,i) => (
        <p key={i} style={{color: p.color}} className="mb-0.5">
          {p.name}: <span className="font-semibold">{typeof p.value === "number" ? p.value.toFixed(2) : p.value}</span>
          {p.unit || ""}
        </p>
      ))}
    </div>
  );
};

// ─── Chart 1 – IASK Evolución Trimestral ────────────────────────────────────
function Chart1() {
  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-700 mb-1">
        Ingreso por ASK (¢ USD) — Evolución trimestral 2021–2025
      </h3>
      <p className="text-xs text-gray-500 mb-3">
        Proxy principal del precio unitario del boleto. Ingresos totales por asiento-kilómetro disponible.
      </p>
      <ResponsiveContainer width="100%" height={260}>
        <AreaChart data={data} margin={{top:5,right:20,left:0,bottom:5}}>
          <defs>
            <linearGradient id="gradIASK" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={AZUL} stopOpacity={0.2}/>
              <stop offset="95%" stopColor={AZUL} stopOpacity={0}/>
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6"/>
          <XAxis dataKey="q" tick={{fontSize:10}} interval={1}/>
          <YAxis domain={[4,11]} tickFormatter={v=>`${v}¢`} tick={{fontSize:10}} width={35}/>
          <Tooltip content={<CustomTip/>}/>
          <ReferenceLine y={9.3} stroke={ROJO} strokeDasharray="4 4"
            label={{value:"Pico 2023", position:"insideTopRight", fontSize:9, fill:ROJO}}/>
          <Area type="monotone" dataKey="iask" stroke={AZUL} strokeWidth={2.5}
            fill="url(#gradIASK)" name="IASK" unit="¢" dot={{r:3,fill:AZUL}}
            activeDot={{r:5}}/>
        </AreaChart>
      </ResponsiveContainer>
      <div className="flex gap-4 mt-2 text-xs text-gray-500">
        <span>▲ Máx: <b className="text-gray-700">10.2¢</b> (4T25)</span>
        <span>▼ Mín: <b className="text-gray-700">4.8¢</b> (1T21 – COVID)</span>
        <span>📈 Crecimiento total: <b className="text-green-600">+115%</b></span>
      </div>
    </div>
  );
}

// ─── Chart 2 – Yield vs IASK ─────────────────────────────────────────────────
function Chart2() {
  const d2 = data.filter(r => r.yield_c !== null);
  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-700 mb-1">
        Yield vs IASK (¢ USD) — 2021–2023
      </h3>
      <p className="text-xs text-gray-500 mb-3">
        Yield = ingreso de pasaje por pasajero-km recorrido (precio "real" por km). IASK incluye todos los ingresos.
      </p>
      <ResponsiveContainer width="100%" height={260}>
        <ComposedChart data={d2} margin={{top:5,right:20,left:0,bottom:5}}>
          <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6"/>
          <XAxis dataKey="q" tick={{fontSize:10}} interval={0}/>
          <YAxis domain={[4,11]} tickFormatter={v=>`${v}¢`} tick={{fontSize:10}} width={35}/>
          <Tooltip content={<CustomTip/>}/>
          <Legend wrapperStyle={{fontSize:11}}/>
          <Line type="monotone" dataKey="iask" stroke={AZUL} strokeWidth={2.5}
            name="IASK (ingreso total/ASK)" unit="¢" dot={{r:3}} activeDot={{r:5}}/>
          <Line type="monotone" dataKey="yield_c" stroke={ROJO} strokeWidth={2.5}
            name="Yield (pasaje/RPK)" unit="¢" dot={{r:3}} activeDot={{r:5}}
            strokeDasharray="5 3"/>
        </ComposedChart>
      </ResponsiveContainer>
      <div className="text-xs text-gray-500 mt-2">
        El Yield superó el IASK en 2021 (vuelos muy llenos, otros ingresos bajos). En 2022–2023 el IASK alcanzó al Yield por incremento de ingresos ancillary.
      </div>
    </div>
  );
}

// ─── Chart 3 – IASK vs CASK (Margen unitario) ───────────────────────────────
function Chart3() {
  const dMarg = data.map(r => ({...r, margen: parseFloat((r.iask - r.cask).toFixed(2))}));
  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-700 mb-1">
        Precio vs Costo por ASK — Margen unitario (¢ USD)
      </h3>
      <p className="text-xs text-gray-500 mb-3">
        IASK (precio) y CASK (costo) por asiento-km. Cuando IASK &gt; CASK la operación es rentable por vuelo.
      </p>
      <ResponsiveContainer width="100%" height={260}>
        <ComposedChart data={dMarg} margin={{top:5,right:20,left:0,bottom:5}}>
          <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6"/>
          <XAxis dataKey="q" tick={{fontSize:10}} interval={1}/>
          <YAxis yAxisId="left" domain={[3,11]} tickFormatter={v=>`${v}¢`} tick={{fontSize:10}} width={35}/>
          <YAxis yAxisId="right" orientation="right" domain={[-3,3]}
            tickFormatter={v=>`${v>0?"+":""}${v}¢`} tick={{fontSize:10}} width={38}/>
          <Tooltip content={<CustomTip/>}/>
          <Legend wrapperStyle={{fontSize:11}}/>
          <Bar yAxisId="right" dataKey="margen" name="Margen IASK-CASK"
            fill={VERDE} opacity={0.35} unit="¢"/>
          <Line yAxisId="left" type="monotone" dataKey="iask" stroke={AZUL}
            strokeWidth={2.5} name="IASK" unit="¢" dot={{r:2}} activeDot={{r:5}}/>
          <Line yAxisId="left" type="monotone" dataKey="cask" stroke={ROJO}
            strokeWidth={2} name="CASK" unit="¢" dot={{r:2}} activeDot={{r:5}}
            strokeDasharray="4 3"/>
          <ReferenceLine yAxisId="right" y={0} stroke="#9CA3AF" strokeWidth={1}/>
        </ComposedChart>
      </ResponsiveContainer>
      <div className="text-xs text-gray-500 mt-2">
        Zona roja (2021–2022 en varios trimestres): CASK &gt; IASK, operación en pérdida unitaria. Desde 3T22 el spread se vuelve positivo y consistente.
      </div>
    </div>
  );
}

// ─── Chart 4 – Precio (IASK) vs Volumen (Pasajeros) ─────────────────────────
function Chart4() {
  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-700 mb-1">
        Precio (IASK) vs Volumen de Pasajeros por trimestre
      </h3>
      <p className="text-xs text-gray-500 mb-3">
        Muestra si Aeroméxico creció en precio, en volumen, o en ambos simultáneamente.
      </p>
      <ResponsiveContainer width="100%" height={260}>
        <ComposedChart data={data} margin={{top:5,right:20,left:0,bottom:5}}>
          <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6"/>
          <XAxis dataKey="q" tick={{fontSize:10}} interval={1}/>
          <YAxis yAxisId="left" domain={[4,11]} tickFormatter={v=>`${v}¢`}
            tick={{fontSize:10}} width={35}/>
          <YAxis yAxisId="right" orientation="right" domain={[2500,7500]}
            tickFormatter={v=>`${(v/1000).toFixed(1)}M`} tick={{fontSize:10}} width={38}/>
          <Tooltip content={<CustomTip/>}/>
          <Legend wrapperStyle={{fontSize:11}}/>
          <Bar yAxisId="right" dataKey="pax" name="Pasajeros (miles)"
            fill={AMBER} opacity={0.45} unit="k"/>
          <Line yAxisId="left" type="monotone" dataKey="iask" stroke={AZUL}
            strokeWidth={2.5} name="IASK" unit="¢" dot={{r:3}} activeDot={{r:5}}/>
        </ComposedChart>
      </ResponsiveContainer>
      <div className="text-xs text-gray-500 mt-2">
        2021: recuperación liderada por precio bajo y bajo volumen. 2022–2024: crecimiento simultáneo de precio y volumen. 2025: ligera caída de precio con estabilización de volumen.
      </div>
    </div>
  );
}

// ─── Chart 5 – Factor de Ocupación vs IASK (scatter) ────────────────────────
function Chart5() {
  const colors = {"2021":ROJO,"2022":AMBER,"2023":VERDE,"2024":AZUL,"2025":"#7C3AED"};
  const byYear = yrs.map(y => ({
    year: y,
    color: colors[y],
    points: data.filter(r=>r.q.includes(y)).map(r=>({q:r.q, x:r.load, y:r.iask}))
  }));
  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-700 mb-1">
        Factor de Ocupación (%) vs IASK (¢ USD) — por año
      </h3>
      <p className="text-xs text-gray-500 mb-3">
        A mayor factor de ocupación, ¿sube el precio? Cada punto es un trimestre; agrupados por año.
      </p>
      <ResponsiveContainer width="100%" height={260}>
        <ScatterChart margin={{top:5,right:20,left:0,bottom:5}}>
          <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6"/>
          <XAxis type="number" dataKey="x" name="Factor Ocup." unit="%"
            domain={[65,92]} tick={{fontSize:10}} label={{value:"Factor de Ocupación (%)",
              position:"insideBottom",offset:-2,fontSize:10}}/>
          <YAxis type="number" dataKey="y" name="IASK" unit="¢"
            domain={[4,11]} tick={{fontSize:10}} width={35}
            label={{value:"IASK (¢)",angle:-90,position:"insideLeft",fontSize:10}}/>
          <Tooltip cursor={{strokeDasharray:"3 3"}}
            content={({active,payload})=>{
              if(!active||!payload?.length) return null;
              const d=payload[0].payload;
              return (
                <div className="bg-white border border-gray-200 rounded-lg shadow p-2 text-xs">
                  <b>{d.q}</b><br/>
                  Ocupación: {d.x}%<br/>
                  IASK: {d.y}¢
                </div>
              );
            }}/>
          <Legend wrapperStyle={{fontSize:11}}/>
          {byYear.map(g=>(
            <Scatter key={g.year} name={g.year} data={g.points} fill={g.color}/>
          ))}
        </ScatterChart>
      </ResponsiveContainer>
      <div className="text-xs text-gray-500 mt-2">
        Correlación positiva clara: al subir el factor de ocupación sube el IASK. Los puntos de 2024–2025 (azul/morado) dominan la esquina superior derecha: más llenos y más caros.
      </div>
    </div>
  );
}

// ─── KPI Cards ───────────────────────────────────────────────────────────────
const kpis = [
  { label:"IASK 4T25",      value:"10.2¢", sub:"Récord histórico",    color:"text-blue-700"  },
  { label:"IASK mínimo",    value:"4.8¢",  sub:"1T21 (COVID)",        color:"text-red-600"   },
  { label:"Crecimiento",    value:"+115%", sub:"1T21 → 4T25",         color:"text-green-600" },
  { label:"Factor Ocup 3T24",value:"88.9%",sub:"Récord de ocupación", color:"text-amber-600" },
  { label:"Pax máximo",     value:"6.7M",  sub:"3T24 (récord)",       color:"text-purple-600"},
];

// ─── Main App ────────────────────────────────────────────────────────────────
export default function App() {
  const [active, setActive] = useState(0);
  const charts = [
    { title:"IASK Trimestral", component:<Chart1/> },
    { title:"Yield vs IASK",   component:<Chart2/> },
    { title:"Precio vs Costo", component:<Chart3/> },
    { title:"Precio vs Volumen",component:<Chart4/>},
    { title:"Ocupación vs Precio",component:<Chart5/>},
  ];

  return (
    <div className="bg-gray-50 min-h-screen p-4 font-sans">
      {/* Header */}
      <div className="bg-white rounded-2xl shadow-sm p-5 mb-4 border border-gray-100">
        <div className="flex items-center gap-3 mb-1">
          <div className="w-2 h-8 rounded-full" style={{background:AZUL}}/>
          <h1 className="text-xl font-bold text-gray-900">
            Aeroméxico — Análisis de Precio del Boleto
          </h1>
        </div>
        <p className="text-xs text-gray-500 ml-5">
          Resultados trimestrales 1T21 – 4T25 · Fuente: Reportes de resultados Grupo Aeroméxico
        </p>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-5 gap-3 mb-4">
        {kpis.map((k,i) => (
          <div key={i} className="bg-white rounded-xl shadow-sm p-3 border border-gray-100 text-center">
            <p className={`text-xl font-extrabold ${k.color}`}>{k.value}</p>
            <p className="text-xs font-semibold text-gray-700 mt-0.5">{k.label}</p>
            <p className="text-xs text-gray-400">{k.sub}</p>
          </div>
        ))}
      </div>

      {/* Tab Nav */}
      <div className="flex gap-2 mb-4 overflow-x-auto">
        {charts.map((c,i) => (
          <button key={i} onClick={()=>setActive(i)}
            className={`px-4 py-2 rounded-lg text-xs font-semibold whitespace-nowrap transition-all
              ${active===i
                ? "text-white shadow-sm"
                : "bg-white text-gray-600 border border-gray-200 hover:bg-gray-50"}`}
            style={active===i ? {background:AZUL} : {}}>
            {i+1}. {c.title}
          </button>
        ))}
      </div>

      {/* Chart Panel */}
      <div className="bg-white rounded-2xl shadow-sm p-5 border border-gray-100">
        {charts[active].component}
      </div>

      {/* Data Table Toggle */}
      <DataTable/>

      {/* Footer */}
      <p className="text-center text-xs text-gray-400 mt-4">
        IASK = Ingreso total / Asiento-km disponible · CASK = Costo total / Asiento-km · Yield = Ingreso pasaje / Pasajero-km recorrido
      </p>
    </div>
  );
}

function DataTable() {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-4 bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
      <button onClick={()=>setOpen(!open)}
        className="w-full px-5 py-3 text-left text-sm font-semibold text-gray-700 flex justify-between items-center hover:bg-gray-50">
        <span>📊 Datos completos por trimestre</span>
        <span className="text-gray-400">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-gray-50 text-gray-600">
                {["Trimestre","IASK (¢)","Yield (¢)","Pasaje/ASK (¢)","CASK (¢)","Margen (¢)","Pasajeros (k)","Factor Ocup (%)"].map(h=>(
                  <th key={h} className="px-3 py-2 text-right first:text-left font-semibold">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.map((r,i)=>{
                const margen = (r.iask - r.cask).toFixed(2);
                const pos = parseFloat(margen) >= 0;
                return (
                  <tr key={i} className={i%2===0?"bg-white":"bg-gray-50/50"}>
                    <td className="px-3 py-1.5 font-semibold text-gray-800">{r.q}</td>
                    <td className="px-3 py-1.5 text-right text-blue-700 font-semibold">{r.iask.toFixed(2)}</td>
                    <td className="px-3 py-1.5 text-right text-red-600">{r.yield_c ?? "—"}</td>
                    <td className="px-3 py-1.5 text-right text-gray-600">{r.ip_ask ?? "—"}</td>
                    <td className="px-3 py-1.5 text-right text-gray-600">{r.cask.toFixed(2)}</td>
                    <td className={`px-3 py-1.5 text-right font-semibold ${pos?"text-green-600":"text-red-500"}`}>
                      {pos?"+":""}{margen}
                    </td>
                    <td className="px-3 py-1.5 text-right text-gray-600">{r.pax.toLocaleString()}</td>
                    <td className="px-3 py-1.5 text-right text-gray-600">{r.load}%</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
