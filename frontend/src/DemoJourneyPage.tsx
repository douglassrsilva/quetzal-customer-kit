import { useEffect, useMemo, useState, type FormEvent } from 'react'
import {
  AlertTriangle, ArrowRight, BrainCircuit, CheckCircle2, ClipboardCheck,
  DollarSign, Network, RefreshCw, Route, ShieldCheck, UserRound,
} from 'lucide-react'
import { api, money, number, post } from './api'

const COUNTRIES = ['ALL','PA','MX','CO','BR','AR','CL','PE','EC','CR','GT','DO','UY']
const FLAGS:Record<string,string>={PA:'🇵🇦',MX:'🇲🇽',CO:'🇨🇴',BR:'🇧🇷',AR:'🇦🇷',CL:'🇨🇱',PE:'🇵🇪',EC:'🇪🇨',CR:'🇨🇷',GT:'🇬🇹',DO:'🇩🇴',UY:'🇺🇾'}
const STEP_DETAILS:Record<string,string>={
  PREFLIGHT:'Confirma Warehouse, Genie, IQ, memoria, AI/BI y permisos sin ejecutar inferencia.',
  INCIDENT:'Revisa severidad, causa probable, SLA y evidencia operacional.',
  VOICE_OF_CUSTOMER:'Identifica temas, presión de experiencia y clientes afectados con evidencia gobernada.',
  CUSTOMER_360:'Abre la historia completa de un cliente prioritario del mismo mercado.',
  RECOMMENDATION:'Entiende los factores del riesgo y conserva la aprobación humana.',
  CAMPAIGN_OPTIMIZER:'Convierte la señal en una audiencia gobernada bajo presupuesto, consentimiento y capacidad.',
  FINANCIAL_IMPACT:'Expone premisas, fórmulas, sensibilidad y retorno estimado.',
}

type Props={
  openIncident:(incidentId:string)=>void
  openCustomer:(customerId:string)=>void
  navigate:(page:'actions'|'intelligence'|'voice'|'campaigns')=>void
}

function severity(value:string){return <span className={`severity ${String(value||'MEDIUM').toLowerCase()}`}>{value||'MEDIUM'}</span>}

export default function DemoJourneyPage({openIncident,openCustomer,navigate}:Props){
  const[country,setCountry]=useState(()=>localStorage.getItem('quetzal-demo-country')||'ALL')
  const[data,setData]=useState<any>(null)
  const[loading,setLoading]=useState(true)
  const[error,setError]=useState('')
  const[nonce,setNonce]=useState(0)
  useEffect(()=>localStorage.setItem('quetzal-demo-country',country),[country])
  useEffect(()=>{
    const controller=new AbortController();setLoading(true);setError('')
    api(`/api/demo/journey?country=${country}`,{signal:controller.signal}).then(setData).catch(err=>{if(err.name!=='AbortError')setError(err.message)}).finally(()=>{if(!controller.signal.aborted)setLoading(false)})
    return()=>controller.abort()
  },[country,nonce])
  const incident=data?.incident||{}
  const customer=data?.customer||{}
  const steps=data?.steps||[]
  function runStep(step:any,index:number){
    const target=String(step.id||step.target||step.action||step.type||'').toUpperCase()
    if(target==='PREFLIGHT')return navigate('intelligence')
    if(target==='INCIDENT')return openIncident(incident.incident_id)
    if(target==='VOICE_OF_CUSTOMER'||target==='VOC'){localStorage.setItem('quetzal-voc-country',country);return navigate('voice')}
    if(target==='CUSTOMER_360'||target==='RECOMMENDATION')return openCustomer(customer.customer_id||customer.cliente_id)
    if(target==='CAMPAIGN_OPTIMIZER'||target==='CAMPAIGN'){localStorage.setItem('quetzal-campaign-country',country);return navigate('campaigns')}
    if(target==='FINANCIAL_IMPACT'){document.querySelector('.financial-lab')?.scrollIntoView({behavior:'smooth',block:'start'});return}
    if(index===0)return navigate('intelligence')
    navigate('actions')
  }
  return <div className="demo-journey stack-lg">
    <section className="journey-intro panel-dark">
      <div><span className="overline"><Route/>FLUJO OPERATIVO</span><h2>De la señal al valor,<br/><em>sin perder el contexto.</em></h2><p>Un caso integrado que conecta operación, cliente, decisión humana y resultado financiero.</p></div>
      <label><span>Escenario por mercado</span><select value={country} onChange={e=>setCountry(e.target.value)}>{COUNTRIES.map(code=><option value={code} key={code}>{code==='ALL'?'Toda LATAM':`${FLAGS[code]} ${code}`}</option>)}</select></label>
    </section>
    {loading&&<div className="state-box"><RefreshCw className="spin"/>Preparando recorrido…</div>}
    {error&&<div className="state-box error"><AlertTriangle/><span><b>No fue posible preparar el recorrido.</b><small>{error}</small></span><button onClick={()=>setNonce(x=>x+1)}>Reintentar</button></div>}
    {!loading&&!error&&data?.available===false&&<div className="state-box"><AlertTriangle/><span><b>No hay un caso disponible para este alcance.</b><small>Selecciona otro mercado o revisa la validación de capacidades.</small></span></div>}
    {!loading&&!error&&data?.available!==false&&<>
      <section className="journey-anchor-grid">
        <article className="panel journey-anchor incident-anchor"><header><span><AlertTriangle/>SEÑAL OPERACIONAL</span>{severity(incident.severity)}</header><h3>{incident.title||'Incidente prioritario'}</h3><p>{incident.incident_id} · {FLAGS[incident.country]} {incident.country}</p><dl><div><dt>Clientes en alcance</dt><dd>{number(incident.affected_customers,true)}</dd></div><div><dt>Valor mensual expuesto</dt><dd>{money(incident.revenue_at_risk)}</dd></div><div><dt>SLA operacional</dt><dd>{incident.sla_status||'—'}</dd></div></dl><button onClick={()=>openIncident(incident.incident_id)}>Abrir incidente <ArrowRight/></button></article>
        <article className="panel journey-link"><Network/><strong>Mismo mercado,<br/>no atribución directa</strong><p>El cliente ilustra el impacto potencial dentro del alcance geográfico. Quetzal no afirma una relación torre–cliente sin una llave de asociación.</p><span><ShieldCheck/>{data?.relationship_semantics?.association_type||'SAME_MARKET_EXAMPLE'}</span></article>
        <article className="panel journey-anchor customer-anchor"><header><span><UserRound/>CLIENTE PRIORITARIO</span><span className="status-pill">{customer.graph_risk_tier||customer.risk_tier||'ALTO RIESGO'}</span></header><h3>{customer.customer_name||customer.nombre_completo||customer.customer_ref||'Cliente seleccionado'}</h3><p>{customer.customer_id||customer.cliente_id} · {FLAGS[customer.country||customer.pais_codigo]} {customer.country||customer.pais_codigo}</p><dl><div><dt>Churn priorizado</dt><dd>{number(Number(customer.churn_probability||customer.baseline_churn_probability||0)*100)}%</dd></div><div><dt>Valor mensual</dt><dd>{money(customer.monthly_revenue||0,false)}</dd></div><div><dt>Próxima decisión</dt><dd>{String(customer.graph_recommended_action||customer.recommended_action||'Revisar 360').replaceAll('_',' ')}</dd></div></dl><button onClick={()=>openCustomer(customer.customer_id||customer.cliente_id)}>Abrir Cliente 360 <ArrowRight/></button></article>
      </section>
      <section className="panel journey-steps"><div className="journey-section-head"><span><Route/>HISTORIA DE DECISIÓN</span><div>{steps.length} pasos · datos sintéticos gobernados</div></div><div className="journey-step-list">{steps.map((step:any,index:number)=><button key={step.id||step.step||index} onClick={()=>runStep(step,index)}><i>{index+1}</i><span><small>{step.eyebrow||`PASO ${index+1}`}</small><b>{step.title||step.label}</b><p>{step.description||step.detail||STEP_DETAILS[step.id]||'Abrir esta etapa del recorrido.'}</p></span><ArrowRight/></button>)}</div></section>
      <FinancialImpact initialCountry={country}/>
    </>}
  </div>
}

function FinancialImpact({initialCountry}:{initialCountry:string}){
  const[treated,setTreated]=useState(1000);const[reduction,setReduction]=useState(15);const[cost,setCost]=useState(8);const[horizon,setHorizon]=useState(12)
  const[result,setResult]=useState<any>(null);const[busy,setBusy]=useState(false);const[error,setError]=useState('')
  useEffect(()=>setResult(null),[initialCountry])
  async function calculate(event:FormEvent){event.preventDefault();setBusy(true);setError('');try{setResult(await post('/api/demo/financial-impact',{country:initialCountry,treated_customers:treated,relative_churn_reduction_pct:reduction,cost_per_contact_usd:cost,horizon_months:horizon}))}catch(err:any){setError(err.message)}finally{setBusy(false)}}
  const metrics=useMemo(()=>{
    const value=result?.result||{}
    return[
      {label:'Churn esperado evitado',value:number(value.estimated_avoided_churners??0),detail:'clientes equivalentes',icon:<UserRound/>},
      {label:'Ingresos protegidos',value:money(value.estimated_retained_revenue_usd??0),detail:`horizonte de ${horizon} meses`,icon:<DollarSign/>},
      {label:'Costo de intervención',value:money(value.estimated_contact_cost_usd??treated*cost),detail:`${number(result?.scope?.treated_customers??treated,true)} contactos`,icon:<ClipboardCheck/>},
      {label:'Beneficio neto',value:money(value.estimated_net_impact_usd??0),detail:`ROI ${value.estimated_roi_pct==null?'—':`${number(value.estimated_roi_pct)}%`}`,icon:<CheckCircle2/>},
    ]
  },[result,horizon,treated,cost])
  return <section className="financial-lab panel"><div className="financial-copy"><span className="overline"><DollarSign/>IMPACTO CONTRAFACTUAL</span><h3>¿Qué valor puede proteger la intervención?</h3><p>Ajusta las premisas. El resultado es una estimación transparente, no una promesa ni una predicción observada.</p><form onSubmit={calculate}><label><span>Clientes tratados</span><input type="number" min="1" max="1000000" value={treated} onChange={e=>setTreated(Number(e.target.value))}/></label><label><span>Reducción relativa de churn</span><input type="number" min="0" max="100" value={reduction} onChange={e=>setReduction(Number(e.target.value))}/><small>%</small></label><label><span>Costo por contacto</span><input type="number" min="0" max="100000" value={cost} onChange={e=>setCost(Number(e.target.value))}/><small>USD</small></label><label><span>Horizonte</span><select value={horizon} onChange={e=>setHorizon(Number(e.target.value))}><option value="3">3 meses</option><option value="6">6 meses</option><option value="12">12 meses</option><option value="24">24 meses</option></select></label><button className="primary" disabled={busy}>{busy?<RefreshCw className="spin"/>:<BrainCircuit/>}Calcular impacto</button></form>{error&&<p className="form-error">{error}</p>}</div><div className="financial-results">{!result?<div className="financial-empty"><DollarSign/><b>Premisas visibles</b><p>Calcula para ver el caso base, las fórmulas y la sensibilidad del resultado.</p></div>:<><div className="financial-metrics">{metrics.map(item=><article key={item.label}>{item.icon}<span><small>{item.label}</small><b>{item.value}</b><em>{item.detail}</em></span></article>)}</div><details><summary><ShieldCheck/>Ver fórmulas y premisas</summary><div className="formula-list">{Object.entries(result.formulas||{}).map(([key,value])=><p key={key}><b>{key.replaceAll('_',' ')}</b><code>{String(value)}</code></p>)}</div><p>{result.disclaimer}</p></details></>}</div></section>
}
