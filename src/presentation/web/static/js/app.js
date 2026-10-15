const sidebarToggle=document.getElementById('sidebar-toggle');
const sidebar=document.getElementById('sidebar');
if(sidebarToggle&&sidebar){
  const narrowScreen=window.matchMedia('(max-width: 900px)');
  if(localStorage.getItem('sidebar-collapsed')==='true')document.body.classList.add('sidebar-collapsed');
  const updateSidebarButton=()=>{
    const expanded=narrowScreen.matches?sidebar.classList.contains('open'):!document.body.classList.contains('sidebar-collapsed');
    sidebarToggle.setAttribute('aria-expanded',String(expanded));
    sidebarToggle.setAttribute('aria-label',expanded?'Ocultar menú':'Mostrar menú');
    sidebarToggle.title=expanded?'Ocultar menú':'Mostrar menú';
  };
  const toggleSidebar=()=>{
    if(narrowScreen.matches)sidebar.classList.toggle('open');
    else{
      document.body.classList.toggle('sidebar-collapsed');
      localStorage.setItem('sidebar-collapsed',String(document.body.classList.contains('sidebar-collapsed')));
    }
    updateSidebarButton();
  };
  sidebarToggle.addEventListener('click',toggleSidebar);
  narrowScreen.addEventListener('change',()=>{sidebar.classList.remove('open');updateSidebarButton()});
  updateSidebarButton();
}
document.getElementById('theme-toggle')?.addEventListener('click',()=>{let html=document.documentElement;html.dataset.bsTheme=html.dataset.bsTheme==='dark'?'light':'dark';localStorage.setItem('theme',html.dataset.bsTheme)});
document.documentElement.dataset.bsTheme=localStorage.getItem('theme')||'light';
document.getElementById('category-view')?.addEventListener('click',()=>document.getElementById('categories').classList.toggle('compact'));
const schemas={rules:['code','name','category','evaluator','pi_id','parameters','severity','active'],'payload-rules':['pi_id','name','json_path','validation_type','parameters','message','severity','stage','active'],thresholds:['pi_id','duration_seconds','started_minutes','no_activity_minutes','min_success_rate','max_errors','max_dq_percent','max_retries','max_duplicates'],windows:['pi_id','weekdays','start_time','end_time','expected_frequency_minutes','tolerance_minutes','timezone','exceptions'],catalog:['code','origin','category','severity','description','recommendation','owner','active'],channels:['name','type','recipients','min_severity','schedule','templates','active','secret_reference']};
const jsonFields=new Set(['parameters','weekdays','exceptions','recipients','schedule','templates']);const boolFields=new Set(['active']);const numberFields=new Set(['duration_seconds','started_minutes','no_activity_minutes','min_success_rate','max_errors','max_dq_percent','max_retries','max_duplicates','expected_frequency_minutes','tolerance_minutes']);
const config=document.getElementById('config-data');const form=document.getElementById('config-form');let configRows=[];
function buildFields(section){const box=document.getElementById('config-fields');if(!box)return;for(const key of schemas[section]||[]){const wrap=document.createElement('div');wrap.className='col-md-4';const label=document.createElement('label');label.className='form-label';label.textContent=key;label.htmlFor='field-'+key;const input=document.createElement('input');input.className='form-control';input.id='field-'+key;input.name=key;input.type=boolFields.has(key)?'checkbox':numberFields.has(key)?'number':'text';if(boolFields.has(key)){input.className='form-check-input d-block'}if(jsonFields.has(key))input.placeholder='JSON';wrap.append(label,input);box.append(wrap)}}
function prettyMetadata(value){if(value==null)return '—';if(typeof value==='string'){try{value=JSON.parse(value)}catch{return value}}return JSON.stringify(value,(key,item)=>item&&typeof item==='object'&&!Array.isArray(item)?Object.fromEntries(Object.entries(item).sort(([a],[b])=>a.localeCompare(b,'es'))):item,2)}
const hiddenTemplateColumns=new Set(['pi_codigo','pi_sist_orig_id','pi_data','pi_schema']);
const templateColumnsKey='template-visible-columns';
function templateColumnLabel(key){return key==='pi_fecha_actividad'?'Fecha_Actividad':key}
function formatTemplateDate(value){
  if(!value)return '—';
  const date=new Date(value);
  if(Number.isNaN(date.getTime()))return String(value);
  const parts=Object.fromEntries(new Intl.DateTimeFormat('en-GB',{timeZone:'America/Lima',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).formatToParts(date).map(part=>[part.type,part.value]));
  return `${parts.day}/${parts.month}/${parts.year} ${parts.hour}:${parts.minute}:${parts.second}`;
}
function visibleTemplateColumns(available){
  try{
    const saved=JSON.parse(localStorage.getItem(templateColumnsKey));
    if(Array.isArray(saved))return new Set(saved.filter(key=>available.includes(key)));
  }catch{}
  return new Set(available.filter(key=>!hiddenTemplateColumns.has(key)));
}
function renderTemplateColumnOptions(available,visible){
  const menu=document.getElementById('template-column-options');
  if(!menu)return;
  menu.replaceChildren();
  for(const key of available){
    const label=document.createElement('label');label.className='form-check d-block mb-1';
    const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.className='form-check-input';checkbox.value=key;checkbox.checked=visible.has(key);
    checkbox.addEventListener('change',()=>{
      const selected=[...menu.querySelectorAll('input:checked')].map(input=>input.value);
      localStorage.setItem(templateColumnsKey,JSON.stringify(selected));
      renderConfig(configRows);
    });
    const caption=document.createElement('span');caption.className='form-check-label';caption.textContent=templateColumnLabel(key);
    label.append(checkbox,caption);menu.append(label);
  }
}
function downloadTemplateJson(row){
  let metadata=row.pi_metadata;
  if(typeof metadata==='string'){
    try{metadata=JSON.parse(metadata)}catch{}
  }
  const blob=new Blob([JSON.stringify(metadata??null,null,2)+'\n'],{type:'application/json;charset=utf-8'});
  const url=URL.createObjectURL(blob);
  const link=document.createElement('a');link.href=url;link.download=`plantilla_${String(row.pi_id??'sin-id').replace(/[^a-zA-Z0-9_-]/g,'_')}.json`;
  document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function renderConfig(rows){
  configRows=Array.isArray(rows)?rows:(rows.items||[]);
  config.replaceChildren();
  if(!configRows.length){config.textContent='No hay registros.';return}
  const isTemplate=config.dataset.section==='templates';
  const available=Object.keys(configRows[0]).filter(key=>isTemplate||!['parameters','templates','schedule','secret_reference'].includes(key));
  const preferred=(config.closest('.card.card-body.mb-3')?.dataset.columnOrder||'').split(',').filter(Boolean);
  const ordered=[...preferred.filter(key=>available.includes(key)),...available.filter(key=>!preferred.includes(key))];
  const visible=isTemplate?visibleTemplateColumns(available):new Set(available);
  if(isTemplate)renderTemplateColumnOptions(ordered,visible);
  const cols=ordered.filter(key=>visible.has(key));
  const table=document.createElement('table');table.className='table table-sm table-hover';
  const head=document.createElement('thead');const hr=document.createElement('tr');
  for(const key of cols){const th=document.createElement('th');th.textContent=isTemplate?templateColumnLabel(key):key;hr.append(th)}
  if(isTemplate){const th=document.createElement('th');th.textContent='JSON';hr.append(th)}
  if(form)hr.append(document.createElement('th'));
  head.append(hr);table.append(head);
  const body=document.createElement('tbody');
  configRows.forEach(row=>{
    const tr=document.createElement('tr');
    for(const key of cols){
      const td=document.createElement('td');
      if(isTemplate&&key==='pi_metadata'){
        const pre=document.createElement('pre');pre.className='template-metadata mb-0 small';pre.textContent=prettyMetadata(row[key]);td.append(pre);
      }else if(isTemplate&&key==='pi_fecha_actividad')td.textContent=formatTemplateDate(row[key]);
      else td.textContent=typeof row[key]==='object'?JSON.stringify(row[key]):String(row[key]??'—');
      tr.append(td);
    }
    if(isTemplate){
      const td=document.createElement('td');const button=document.createElement('button');
      button.type='button';button.className='btn btn-sm btn-outline-primary text-nowrap';button.title='Descargar pi_metadata en JSON';button.setAttribute('aria-label',`Descargar JSON de la plantilla ${row.pi_id}`);
      button.innerHTML='<i class="bi bi-download" aria-hidden="true"></i> JSON';
      button.addEventListener('click',()=>downloadTemplateJson(row));td.append(button);tr.append(td);
    }
    if(form){
      const td=document.createElement('td');const button=document.createElement('button');button.className='btn btn-sm btn-outline-primary';button.textContent='Editar';
      button.addEventListener('click',()=>{form.dataset.id=row.id;for(const key of schemas[form.dataset.section]||[]){const input=form.elements.namedItem(key);if(input)if(boolFields.has(key))input.checked=Boolean(row[key]);else input.value=typeof row[key]==='object'?JSON.stringify(row[key]):row[key]??''}form.scrollIntoView({behavior:'smooth'})});td.append(button);tr.append(td);
    }
    body.append(tr);
  });
  table.append(body);config.append(table);
}
if(config){const section=config.dataset.section;buildFields(section);fetch('/api/v1/config/'+(section==='templates'?'integration-templates':section)).then(r=>r.json()).then(renderConfig).catch(()=>config.textContent='No se pudo cargar la configuración')}
form?.addEventListener('reset',()=>delete form.dataset.id);
form?.addEventListener('submit',async e=>{e.preventDefault();const data={};const msg=document.getElementById('config-message');try{for(const key of schemas[form.dataset.section]||[]){const input=form.elements.namedItem(key);if(boolFields.has(key))data[key]=input.checked;else if(input.value.trim())data[key]=jsonFields.has(key)?JSON.parse(input.value):numberFields.has(key)?Number(input.value):input.value}const id=form.dataset.id;const response=await fetch('/api/v1/config/'+form.dataset.section+(id?'/'+id:''),{method:id?'PUT':'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':document.querySelector('meta[name="csrf-token"]').content},body:JSON.stringify(data)});const result=await response.json();if(!response.ok)throw Error(JSON.stringify(result));msg.textContent='Guardado correctamente';form.reset();const refreshed=await fetch('/api/v1/config/'+form.dataset.section);renderConfig(await refreshed.json())}catch(error){msg.textContent='No se pudo guardar: '+error.message}});
function showLoading(){const overlay=document.getElementById('loading-overlay');if(!overlay)return;overlay.hidden=false;document.body.setAttribute('aria-busy','true')}
function hideLoading(){const overlay=document.getElementById('loading-overlay');if(overlay)overlay.hidden=true;document.body.removeAttribute('aria-busy')}
document.addEventListener('submit',event=>{if(!event.target.matches('form[data-loading]'))return;const action=event.submitter?.formAction||event.target.action;if(new URL(action,location.href).pathname==='/payloads/export'){hideLoading();return}showLoading()});
document.addEventListener('click',event=>{if(event.target.closest('[data-download]')){hideLoading();return}const link=event.target.closest('a[data-loading]');if(link&&!event.defaultPrevented&&event.button===0&&!event.ctrlKey&&!event.metaKey&&!event.shiftKey&&!event.altKey&&link.target!=='_blank')showLoading()});
window.addEventListener('pageshow',hideLoading);
