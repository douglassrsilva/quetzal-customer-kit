import { useEffect, useMemo, useState } from 'react'
import {
  AlertTriangle, ArrowLeft, ArrowRight, BrainCircuit, ChevronLeft, ChevronRight, Clock3,
  Database, Globe2, Headphones, Lightbulb, Network, PackageOpen, Play, RefreshCw,
  ShieldCheck, TrendingUp, UserRoundSearch, UsersRound,
} from 'lucide-react'
import { api, money, number, post } from './api'
import GraphViewport from './GraphViewport'
import {
  graphNodeId, graphNodeLabel, graphNodeType, graphRunFromResponse, graphRunId,
  graphScorePercent, type GraphGroupMember, type GraphGroupOperationalPayload,
  type GraphGroupSort, type GraphLevel, type GraphMethodology, type GraphNode, type GraphPayload, type GraphRun,
} from './graphTypes'

const COUNTRIES=['ALL','PA','MX','CO','BR','AR','CL','PE','EC','CR','GT','DO','UY']
const TERMINAL=new Set(['SUCCESS','SUCCEEDED','COMPLETED','FAILED','CANCELED','CANCELLED','SKIPPED','TIMEDOUT','INTERNAL_ERROR','BLOCKED','UPSTREAM_FAILED'])
const SUCCESS=new Set(['SUCCESS','SUCCEEDED','COMPLETED'])
const PAGE_SIZE=10
const ACTION_LABELS:Record<string,string>={
  SERVICE_RECOVERY:'Recuperar servicio',RETENTION:'Retención prioritaria',NPS_RECOVERY:'Recuperar NPS',
  PAYMENT_ASSISTANCE:'Alternativa de pago',RETENTION_OFFER:'Oferta de permanencia',CROSS_SELL:'Venta cruzada',
  UPSELL:'Evolución de plan',MONITOR:'Monitorear',
}
const RISK_LABELS:Record<string,string>={CRITICAL:'Crítico',HIGH:'Alto',MEDIUM:'Medio',LOW:'Bajo'}

const percent=(value:unknown)=>`${number(Number(value||0)*100)}%`
const riskClass=(value:unknown)=>String(value||'LOW').toLowerCase()

export default function GraphExplorerPage({openCustomer,canRun}:{openCustomer:(customerId:string)=>void;canRun:boolean}) {
  const [level,setLevel]=useState<GraphLevel>('community')
  const [country,setCountry]=useState('ALL')
  const [riskTier,setRiskTier]=useState('ALL')
  const [communityId,setCommunityId]=useState('')
  const [selected,setSelected]=useState<GraphNode|null>(null)
  const [data,setData]=useState<GraphPayload|null>(null)
  const [loading,setLoading]=useState(true)
  const [error,setError]=useState('')
  const [nonce,setNonce]=useState(0)
  const [run,setRun]=useState<GraphRun|null>(null)
  const [runBusy,setRunBusy]=useState(false)
  const [methodology,setMethodology]=useState<GraphMethodology|null>(null)
  const [operations,setOperations]=useState<GraphGroupOperationalPayload|null>(null)
  const [operationsLoading,setOperationsLoading]=useState(false)
  const [operationsError,setOperationsError]=useState('')
  const [sort,setSort]=useState<GraphGroupSort>('priority')
  const [offset,setOffset]=useState(0)
  const limit=level==='community'?45:120
  const selectedGroupId=selected&&graphNodeType(selected)==='community'?String(selected.community_id||graphNodeId(selected)):''

  useEffect(()=>{
    api<GraphRun|{run?:GraphRun;workflow?:GraphRun;snapshot?:GraphRun}>('/api/graph/runs/latest').then(value=>setRun(graphRunFromResponse(value))).catch(()=>undefined)
    api<GraphMethodology>('/api/graph/methodology').then(setMethodology).catch(()=>undefined)
  },[])

  useEffect(()=>{
    const controller=new AbortController();setLoading(true);setError('');setSelected(null);setOperations(null)
    const params=new URLSearchParams({level,country,risk_tier:riskTier,limit:String(limit)})
    if(communityId)params.set('community_id',communityId)
    api<GraphPayload>(`/api/graph/network?${params}`,{signal:controller.signal}).then(setData).catch(error=>{if(error.name!=='AbortError')setError(error.message)}).finally(()=>{if(!controller.signal.aborted)setLoading(false)})
    return()=>controller.abort()
  },[level,country,riskTier,communityId,limit,nonce])

  useEffect(()=>{
    if(!selectedGroupId){setOperations(null);setOperationsError('');return}
    const controller=new AbortController();setOperationsLoading(true);setOperationsError('')
    const params=new URLSearchParams({country,risk_tier:riskTier,sort,limit:String(PAGE_SIZE),offset:String(offset)})
    api<GraphGroupOperationalPayload>(`/api/graph/communities/${encodeURIComponent(selectedGroupId)}/operational?${params}`,{signal:controller.signal})
      .then(setOperations).catch(error=>{if(error.name!=='AbortError')setOperationsError(error.message)})
      .finally(()=>{if(!controller.signal.aborted)setOperationsLoading(false)})
    return()=>controller.abort()
  },[selectedGroupId,country,riskTier,sort,offset])

  const activeRunId=graphRunId(run)
  const runStatus=String(run?.status||'').toUpperCase()
  useEffect(()=>{
    if(!activeRunId||TERMINAL.has(runStatus))return
    const timer=window.setInterval(()=>api<GraphRun|{run?:GraphRun;workflow?:GraphRun;snapshot?:GraphRun}>(`/api/graph/runs/${encodeURIComponent(activeRunId)}`).then(value=>{const next=graphRunFromResponse(value);setRun(next);const status=String(next.status||'').toUpperCase();if(TERMINAL.has(status)){setRunBusy(false);if(SUCCESS.has(status))setNonce(value=>value+1)}}).catch(()=>setRunBusy(false)),3000)
    return()=>window.clearInterval(timer)
  },[activeRunId,runStatus])

  async function startRun(){setRunBusy(true);try{const value=await post<GraphRun|{run?:GraphRun;workflow?:GraphRun;snapshot?:GraphRun}>('/api/graph/runs',{});setRun(graphRunFromResponse(value))}catch(error){setRun({status:'FAILED',error:error instanceof Error?error.message:'No fue posible iniciar la ejecución.'});setRunBusy(false)}}
  function selectNode(node:GraphNode){setSelected(node);setOffset(0);setSort('priority')}
  function drill(node:GraphNode){const id=String(node.community_id||graphNodeId(node));setCommunityId(id);setLevel('customer')}
  function backToGroups(){setLevel('community');setCommunityId('');setSelected(null)}
  const summary=data?.summary||{}
  const computedAt=data?.run?.computed_at||data?.computed_at||run?.completed_at||run?.computed_at
  const selectedId=selected?graphNodeId(selected):''
  const statusLabel=useMemo(()=>runStatus||'SIN EJECUCIÓN',[runStatus])

  return <div className="graph-explorer stack-lg">
    <section className="graph-run-banner panel"><div><span className={`run-signal ${SUCCESS.has(runStatus)?'success':TERMINAL.has(runStatus)&&runStatus?'failed':'running'}`}><i/><b>{statusLabel}</b></span><p><strong>Procesamiento bajo demanda</strong><small>Genera relaciones ponderadas, señales separadas y el grafo semántico OntoBricks. No existe programación recurrente.</small></p></div><div><span><Clock3/><small>{computedAt?`Último snapshot: ${new Date(String(computedAt)).toLocaleString('es-419')}`:'Sin snapshot calculado'}</small></span>{canRun?<button className="primary" disabled={runBusy||(!TERMINAL.has(runStatus)&&!!runStatus)} onClick={startRun}>{runBusy||(!TERMINAL.has(runStatus)&&!!runStatus)?<RefreshCw className="spin"/>:<Play/>}{runBusy||(!TERMINAL.has(runStatus)&&!!runStatus)?'Procesando…':'Actualizar Graph Intelligence'}</button>:<small className="graph-run-restricted"><ShieldCheck/>Actualización reservada a administradores</small>}</div>{run?.error&&<p className="graph-run-error">{run.error}</p>}</section>
    {methodology&&<section className="panel graph-methodology">
      <header><div><span><BrainCircuit/>{methodology.status==='ACTIVE'?'MÉTODO ACTIVO':'MÉTODO V3 OBJETIVO'}</span><h3>Churn, exposición y alcance son señales distintas</h3><p>PageRank no calcula churn. El modelo individual conserva la probabilidad; el grafo ordena alcance, exposición y prioridad operacional.</p></div><em className={methodology.status==='ACTIVE'?'active':'pending'}>{methodology.status==='ACTIVE'?'V3 ACTIVO':'REFRESH MANUAL PENDIENTE'}</em></header>
      <div className="graph-method-grid">{methodology.algorithms.slice(0,4).map(item=><article key={item.id}><small>{item.output}</small><b>{item.label}</b><span>{item.algorithm}</span><p>{item.role}</p></article>)}</div>
      <footer><span><Database/><b>OntoBricks {methodology.ontobricks.version.split('+')[0]}</b> · {methodology.ontobricks.triple_table}</span><p>{methodology.relationship.semantics}</p>{methodology.ontobricks.external_app_url&&<a href={methodology.ontobricks.external_app_url} target="_blank" rel="noreferrer">Abrir OntoBricks <ArrowRight/></a>}</footer>
    </section>}
    <div className="graph-explorer-toolbar panel">
      <div>{level==='customer'&&<button className="graph-back" onClick={backToGroups}><ArrowLeft/>Grupos</button>}<label><span>Nivel</span><select value={level} onChange={event=>{setLevel(event.target.value as GraphLevel);if(event.target.value==='community')setCommunityId('')}}><option value="community">Grupos de relación</option><option value="customer" disabled={!communityId}>Clientes del grupo</option></select></label><label><span>Mercado</span><select value={country} onChange={event=>setCountry(event.target.value)}>{COUNTRIES.map(item=><option key={item} value={item}>{item==='ALL'?'Toda LATAM':item}</option>)}</select></label><label><span>Riesgo</span><select value={riskTier} onChange={event=>setRiskTier(event.target.value)}><option value="ALL">Todos</option><option value="CRITICAL">Crítico</option><option value="HIGH">Alto</option><option value="MEDIUM">Medio</option><option value="LOW">Bajo</option></select></label></div><span><ShieldCheck/>Vista gobernada · máximo {limit} nodos</span>
    </div>
    <section className="graph-overview-kpis">
      <article><UsersRound/><span><small>{level==='community'?'Grupos visibles':'Clientes visibles'}</small><b>{number(summary.total_nodes??summary.nodes??data?.nodes?.length??0)}</b></span></article>
      <article><Network/><span><small>Conexiones visibles</small><b>{number(summary.total_edges??summary.edges??data?.edges?.length??0)}</b></span></article>
      <article><AlertTriangle/><span><small>Clientes de alto riesgo</small><b>{number(summary.high_risk_customers??0,true)}</b></span></article>
      <article><Globe2/><span><small>Valor en relaciones</small><b>{money(summary.influenced_revenue_usd??summary.influenced_revenue??0)}</b></span></article>
    </section>
    <section className="graph-explorer-layout">
      <div className="panel graph-explorer-canvas">
        <header><div><span>{level==='community'?'ALCANCE REGIONAL':'RED DEL GRUPO'}</span><h3>{level==='community'?'Grupos de relación sin fronteras':communityId||'Clientes conectados'}</h3></div><small>{data?.nodes?.length||0} nodos · {data?.edges?.length||0} conexiones</small></header>
        {loading&&<div className="graph-state"><RefreshCw className="spin"/>Construyendo la red visible…</div>}
        {error&&<div className="graph-state error"><AlertTriangle/><span><b>No fue posible cargar la red.</b><small>{error}</small></span><button onClick={()=>setNonce(value=>value+1)}>Reintentar</button></div>}
        {!loading&&!error&&data?.available===false&&<div className="graph-state"><Network/><span><b>No hay un snapshot de Graph Intelligence.</b><small>{data.message||'Usa el botón de actualización manual para generar los datos.'}</small></span></div>}
        {!loading&&!error&&data&&data.available!==false&&<GraphViewport nodes={data.nodes||[]} edges={data.edges||[]} level={level} selectedId={selectedId} onSelect={selectNode} ariaLabel={level==='community'?'Red de grupos de relación':'Red de clientes del grupo'}/>} 
      </div>
      <aside className="panel graph-explorer-detail">
        {!selected&&<div className="graph-detail-empty"><Network/><b>Del patrón a la acción</b><p>Selecciona un grupo para ver sus clientes, prioridades, ofertas y playbooks.</p></div>}
        {selected&&<><span>{graphNodeType(selected)==='community'?'GRUPO DE RELACIÓN':'CLIENTE'}</span><h3>{graphNodeLabel(selected)}</h3><p>{selected.country?`Mercado principal: ${selected.country}`:'Relación regional gobernada'}</p><dl><div><dt>Clientes</dt><dd>{number(selected.customers??selected.customer_count??1,true)}</dd></div><div><dt>Alto riesgo</dt><dd>{number(selected.high_risk_customers??0,true)}</dd></div><div><dt>Churn individual</dt><dd>{percent(selected.baseline_churn_probability??selected.churn_probability)}</dd></div><div><dt>Alcance</dt><dd>{number(graphScorePercent(selected.reach_score??selected.influence_score))}%</dd></div><div><dt>Exposición relacional</dt><dd>{number(graphScorePercent(selected.network_exposure_score??selected.contagion_score))}%</dd></div><div><dt>Países alcanzados</dt><dd>{number(selected.countries_reached??0)}</dd></div></dl>{graphNodeType(selected)==='community'?<button onClick={()=>drill(selected)}>Ver red de clientes <ArrowRight/></button>:<button onClick={()=>openCustomer(graphNodeId(selected))}>Abrir Cliente 360 <ArrowRight/></button>}{graphNodeType(selected)==='community'&&<small className="graph-technical-id">Referencia técnica · {graphNodeId(selected)}</small>}</>}
      </aside>
    </section>
    {selectedGroupId&&<GroupOperations payload={operations} loading={operationsLoading} error={operationsError} sort={sort} setSort={value=>{setSort(value);setOffset(0)}} offset={offset} setOffset={setOffset} openCustomer={openCustomer}/>} 
  </div>
}

function GroupOperations({payload,loading,error,sort,setSort,offset,setOffset,openCustomer}:{payload:GraphGroupOperationalPayload|null;loading:boolean;error:string;sort:GraphGroupSort;setSort:(value:GraphGroupSort)=>void;offset:number;setOffset:(value:number)=>void;openCustomer:(customerId:string)=>void}){
  const group=payload?.group
  const pagination=payload?.pagination
  const total=Number(pagination?.total||0)
  const from=total?offset+1:0
  const to=Math.min(offset+PAGE_SIZE,total)
  if(loading)return <section className="panel group-operations-state"><RefreshCw className="spin"/><b>Preparando la mesa operativa del grupo…</b></section>
  if(error)return <section className="panel group-operations-state error"><AlertTriangle/><span><b>No fue posible cargar la operación del grupo.</b><small>{error}</small></span></section>
  if(payload?.available===false)return <section className="panel group-operations-state"><AlertTriangle/><span><b>Los datos operativos todavía no están disponibles.</b><small>La red permanece visible, pero perfiles u ofertas necesitan ser preparados.</small></span></section>
  if(!payload||!group)return null
  return <section className="group-operations stack-lg" aria-label={`Mesa operativa ${group.display_name}`}>
    <header className="panel group-operations-head"><div><span>MESA OPERATIVA DEL GRUPO</span><h2>{group.display_name}</h2><p>Clientes priorizados individualmente, con acción recomendada y oferta elegible. <small>{group.technical_id}</small></p></div><div><span><ShieldCheck/>Datos limitados a tu alcance territorial</span><label>Ordenar por<select value={sort} onChange={event=>setSort(event.target.value as GraphGroupSort)}><option value="priority">Riesgo y prioridad</option><option value="opportunity">Oportunidad comercial</option><option value="influence">Alcance en la red</option></select></label></div></header>
    <div className="group-operations-kpis">
      <article><UsersRound/><span><small>Clientes visibles</small><b>{number(group.customer_count,true)}</b></span></article>
      <article><AlertTriangle/><span><small>Alto riesgo</small><b>{number(group.high_risk_customers,true)}</b></span></article>
      <article><TrendingUp/><span><small>Ingresos mensuales</small><b>{money(group.monthly_revenue_usd)}</b></span></article>
      <article><ShieldCheck/><span><small>Ingresos en riesgo</small><b>{money(group.monthly_revenue_at_risk_usd)}</b></span></article>
      <article><Headphones/><span><small>Presión de SLA</small><b>{number(group.customers_with_sla_pressure,true)}</b></span></article>
      <article><UserRoundSearch/><span><small>Detractores NPS</small><b>{number(group.detractors,true)}</b></span></article>
    </div>
    <div className="group-action-grid">
      <section className="panel group-playbooks"><header><Lightbulb/><div><span>QUÉ HACER</span><h3>Playbooks recomendados</h3></div></header>{payload.playbooks.length?<div>{payload.playbooks.map(item=><article key={item.type}><span className={`priority ${item.priority.toLowerCase()}`}>{item.priority}</span><div><h4>{item.title}</h4><p>{item.reason}</p><strong>{item.action}</strong><small>{number(item.audience)} cliente(s) elegible(s) · requiere validación humana</small></div></article>)}</div>:<p className="group-empty">No hay una intervención colectiva urgente para este filtro.</p>}</section>
      <section className="panel group-offers"><header><PackageOpen/><div><span>QUÉ PROPONER</span><h3>Productos con mejor encaje</h3></div></header>{payload.offers.length?<div>{payload.offers.map(offer=><article key={offer.plan_id}><div><span>{offer.vertical||'Producto'}</span><h4>{offer.product_name}</h4><p>{offer.reason||'Oferta elegible según portafolio y perfil del cliente.'}</p></div><dl><div><dt>Elegibles</dt><dd>{number(offer.eligible_customers)}</dd></div><div><dt>Precio</dt><dd>{money(offer.price_usd,false)}</dd></div><div><dt>Afinidad</dt><dd>{number(offer.avg_score)}%</dd></div></dl></article>)}</div>:<p className="group-empty">No hay ofertas elegibles con consentimiento para este filtro.</p>}</section>
    </div>
    <section className="panel group-members">
      <header><div><span>QUIÉNES SON</span><h3>Clientes para actuar ahora</h3></div><small>{from}–{to} de {number(total)} clientes</small></header>
      <div className="group-members-scroll"><table><thead><tr><th>Cliente</th><th>Plan actual</th><th>Churn individual</th><th>Alcance</th><th>NPS</th><th>SLA / tickets</th><th>Próxima acción</th><th>Producto propuesto</th><th></th></tr></thead><tbody>{payload.members.map(member=><MemberRow key={member.customer_id} member={member} openCustomer={openCustomer}/>)}</tbody></table></div>
      <div className="group-members-mobile">{payload.members.map(member=><MemberCard key={member.customer_id} member={member} openCustomer={openCustomer}/>)}</div>
      {!payload.members.length&&<p className="group-empty">No hay clientes para el filtro seleccionado.</p>}
      <footer><span>Identidad enmascarada hasta abrir el perfil gobernado.</span><div><button disabled={offset===0} onClick={()=>setOffset(Math.max(0,offset-PAGE_SIZE))}><ChevronLeft/>Anterior</button><button disabled={offset+PAGE_SIZE>=total} onClick={()=>setOffset(offset+PAGE_SIZE)}>Siguiente<ChevronRight/></button></div></footer>
    </section>
  </section>
}

function MemberRow({member,openCustomer}:{member:GraphGroupMember;openCustomer:(customerId:string)=>void}){
  return <tr><td><button className="member-link" onClick={()=>openCustomer(member.customer_id)}><b>{member.customer_ref}</b><small>{member.country} · {member.segment||'—'}</small></button></td><td><b>{member.current_plan||'Sin plan activo'}</b><small>{money(member.monthly_revenue,false)}/mes</small></td><td><span className={`risk-chip ${riskClass(member.risk_tier)}`}>{RISK_LABELS[String(member.risk_tier)]||member.risk_tier}</span><small>{percent(member.churn_probability)}</small></td><td><b>{number(graphScorePercent(member.influence_score))}%</b></td><td><b>{member.nps_ultimo??'—'}</b></td><td><span className={`sla-chip ${String(member.sla_status||'').toLowerCase()}`}>{member.sla_status==='AT_RISK'?'En riesgo':member.sla_status==='OPEN'?'Abierto':'En objetivo'}</span><small>{number(member.open_tickets)} ticket(s)</small></td><td><b>{ACTION_LABELS[String(member.next_best_action)]||member.next_best_action||'Monitorear'}</b></td><td>{member.proposed_product?<><b>{member.proposed_product}</b><small>{money(member.proposed_price_usd,false)} · afinidad {number(member.offer_score)}%</small></>:<small>No ofertar antes de resolver la fricción</small>}</td><td><button className="open-360" onClick={()=>openCustomer(member.customer_id)} aria-label={`Abrir Cliente 360 ${member.customer_ref}`}>Cliente 360<ArrowRight/></button></td></tr>
}

function MemberCard({member,openCustomer}:{member:GraphGroupMember;openCustomer:(customerId:string)=>void}){
  return <article><header><button className="member-link" onClick={()=>openCustomer(member.customer_id)}><b>{member.customer_ref}</b><small>{member.country} · {member.segment||'—'}</small></button><span className={`risk-chip ${riskClass(member.risk_tier)}`}>{RISK_LABELS[String(member.risk_tier)]||member.risk_tier} · {percent(member.churn_probability)}</span></header><dl><div><dt>Plan actual</dt><dd>{member.current_plan||'Sin plan activo'}<small>{money(member.monthly_revenue,false)}/mes</small></dd></div><div><dt>Alcance</dt><dd>{number(graphScorePercent(member.influence_score))}%</dd></div><div><dt>NPS</dt><dd>{member.nps_ultimo??'—'}</dd></div><div><dt>SLA</dt><dd><span className={`sla-chip ${String(member.sla_status||'').toLowerCase()}`}>{member.sla_status==='AT_RISK'?'En riesgo':member.sla_status==='OPEN'?'Abierto':'En objetivo'}</span><small>{number(member.open_tickets)} ticket(s)</small></dd></div></dl><section><span>PRÓXIMA ACCIÓN</span><b>{ACTION_LABELS[String(member.next_best_action)]||member.next_best_action||'Monitorear'}</b><small>{member.proposed_product?`${member.proposed_product} · ${money(member.proposed_price_usd,false)} · afinidad ${number(member.offer_score)}%`:'No ofertar antes de resolver la fricción'}</small></section><button className="open-360" onClick={()=>openCustomer(member.customer_id)}>Abrir Cliente 360<ArrowRight/></button></article>
}
