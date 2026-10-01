const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icon = name => `<i data-lucide="${name}"></i>`;
const statusNames = {applied:'Applied',needs_review:'Needs review',queued:'Queued',running:'In progress',skipped:'Skipped'};
let state = null, filter = 'all', selected = null, settingsLoaded = false, visibleLimit = 200;
function icons(){ lucide.createIcons(); }
function notify(message, error=false){ $('notice').hidden=false; $('notice').textContent=message; $('notice').classList.toggle('error',error); }
async function api(path, data){
 const response = await fetch('/api/'+path, data === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json','X-Local-Request':'job-agent'},body:JSON.stringify(data)});
 const result = await response.json();
 if(!response.ok) throw new Error(typeof result.detail==='string'?result.detail:JSON.stringify(result.detail));
 return result;
}
function action(fn){ return async event => {if(event)event.preventDefault();try{await fn(event);}catch(error){notify(error.message,true);}}; }
function view(name){
 document.querySelectorAll('.view').forEach(el=>el.hidden=el.id!==name);
 document.querySelectorAll('.nav').forEach(el=>el.classList.toggle('active',el.dataset.view===name));
 $('heading').textContent={applications:'Applications',profile:'Profile & resumes',activity:'Activity',settings:'Settings'}[name];
}
function date(value){return value?new Date(value).toLocaleString(undefined,{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'}):'';}
function renderJobs(){
 const query=$('search').value.toLowerCase();
 const rows=state.jobs.filter(j=>(filter==='all'||j.status===filter||(filter==='queued'&&j.status==='running'))&&`${j.company} ${j.title} ${j.location}`.toLowerCase().includes(query));
 $('jobs').innerHTML=rows.slice(0,visibleLimit).map(j=>`<tr><td><strong>${esc(j.company)}</strong><span class="role">${esc(j.title)}</span></td><td>${esc(j.location)}</td><td><span class="badge ${j.status}">${statusNames[j.status]}</span></td><td>${esc({sde:'SDE',aiml:'AI / ML',ds:'IT / Cloud'}[j.resume]||'Pending')}</td><td>${esc(date(j.updated))}</td><td><button data-job="${j.id}" title="View application" aria-label="View application at ${esc(j.company)}">${icon('arrow-up-right')}</button></td></tr>`).join('');
 $('more').hidden=rows.length<=visibleLimit;
 $('more').textContent=`Show more (${Math.min(visibleLimit,rows.length)} of ${rows.length})`;
 $('empty').hidden=rows.length>0;
 $('empty').querySelector('h2').textContent=state.jobs.length?'No matching applications':'No applications yet';
 $('empty').querySelector('p').textContent=state.jobs.length?'Try another status or search.':'Your application queue is empty.';
 $('jobs').querySelectorAll('[data-job]').forEach(b=>b.onclick=action(()=>openJob(b.dataset.job)));
 icons();
}
function render(){
 $('identity').textContent=state.profile.email||'Profile not imported';
 $('worker').textContent=state.worker;
 $('auto').innerHTML=icon(state.settings.enabled?'pause':'play')+`<span>${state.settings.enabled?'Pause autopilot':'Enable autopilot'}</span>`;
 for(const [id,status] of [['applied','applied'],['review','needs_review'],['queued','queued']]) $('count-'+id).textContent=state.jobs.filter(j=>j.status===status).length;
 const missing=[!state.connections.openai&&'OpenAI',!state.connections.gmail&&'Gmail'].filter(Boolean);
 $('setup-banner').hidden=!missing.length;
 $('setup-text').textContent=missing.join(' and ')+' not connected. Autopilot is paused.';
 $('key-state').textContent=state.connections.openai?'API key saved':'No API key saved';
 $('gmail-state').textContent=state.connections.gmail?'Gmail authorized':state.connections.gmail_client?'OAuth client ready. Connect your Gmail account.':'OAuth client missing: secrets/gmail-client.json';
 $('adzuna-state').textContent=state.connections.adzuna?'Credentials saved':'Not configured';
 const labels={name:'Name',email:'Email',phone:'Phone',location:'Location',linkedin:'LinkedIn',github:'GitHub'};
 $('profile-values').innerHTML=Object.entries(labels).map(([key,label])=>`<dt>${label}</dt><dd>${esc(state.profile[key]||'Not provided')}</dd>`).join('');
 $('resumes').innerHTML=Object.entries(state.resumes).map(([key,r])=>`<div class="resume">${icon('file-text')}<div><strong>${esc(r.role)}</strong><p>${r.exists?(r.enabled?'Available for applications':'Reference document'):'File missing'}</p></div></div>`).join('');
 $('events').innerHTML=state.events.map(e=>`<div class="event"><time>${esc(date(e.created))}</time><span>${esc(e.message)}</span></div>`).join('')||'<p>No activity recorded.</p>';
 $('deliveries').innerHTML=state.reports.map(r=>`<div class="event"><time>${esc(r.day)}</time><span>${esc(r.status==='sending'?'Delivery pending confirmation':r.status)}</span></div>`).join('')||'<p>No reports sent.</p>';
 if(!settingsLoaded){
  $('limit').value=state.settings.daily_limit;$('interval').value=state.settings.interval_minutes;$('hour').value=state.settings.report_hour;
  $('timezone').value=state.settings.timezone;$('model').value=state.settings.model;
  $('companies').value=state.settings.review_companies.join('\n');$('sources').value=JSON.stringify(state.settings.sources,null,2);settingsLoaded=true;
 }
 renderJobs();icons();
}
async function refresh(){state=await api('state');render();}
async function openJob(id){
 selected=await api('jobs/'+id);if(!selected)return;
 const j=selected;
 $('job-title').textContent=j.company+' / '+j.title;
 const safeUrl=j.url.startsWith('https://')?j.url:'#';
 $('job-detail').innerHTML=`<span class="badge ${j.status}">${statusNames[j.status]}</span><p>${esc(j.reason||'Awaiting evaluation')}</p><p>${esc(j.location)} &nbsp; <a href="${esc(safeUrl)}" target="_blank" rel="noreferrer">Open posting</a>${j.evidence?` &nbsp; <a href="/api/evidence/${j.id}" target="_blank" rel="noreferrer">View screenshot</a>`:''}</p><details><summary>Job description</summary><p class="description">${esc(j.description)}</p></details>`;
 const questions=JSON.parse(j.questions||'[]');
 $('questions').innerHTML=questions.map((q,i)=>`<label>${esc(q)}<textarea data-question="${esc(q)}" rows="2"></textarea></label>`).join('');
 $('resolve-form').hidden=!['needs_review','skipped'].includes(j.status);
 $('retry-confirm').hidden=!j.attempted;$('not-submitted').checked=false;
 $('job-dialog').showModal();
}
document.querySelectorAll('.nav').forEach(b=>b.onclick=()=>view(b.dataset.view));
document.querySelectorAll('.tabs button').forEach(b=>b.onclick=()=>{filter=b.dataset.filter;document.querySelectorAll('.tabs button').forEach(t=>{t.classList.toggle('selected',t===b);t.setAttribute('aria-selected',String(t===b));});renderJobs();});
document.querySelectorAll('.close').forEach(b=>b.onclick=()=>b.closest('dialog').close());
$('search').oninput=()=>state&&renderJobs();
$('more').onclick=()=>{visibleLimit+=200;renderJobs();};
$('open-settings').onclick=()=>view('settings');
$('add').onclick=()=>$('add-dialog').showModal();
for(const [id,cmd] of [['discover','discover'],['empty-discover','discover'],['run','run'],['report','report']]) $(id).onclick=action(async()=>{await api('commands/'+cmd,{});notify(cmd==='report'?'Report queued.':'Worker command queued.');await refresh();});
$('auto').onclick=action(async()=>{await api('settings',{...state.settings,enabled:!state.settings.enabled});notify(state.settings.enabled?'Autopilot paused.':'Autopilot enabled.');await refresh();});
$('key-form').onsubmit=action(async()=>{await api('credentials',{name:'OPENAI_API_KEY',value:$('api-key').value});$('api-key').value='';notify('API key saved in your system credential vault.');await refresh();});
$('adzuna-form').onsubmit=action(async()=>{await api('credentials',{name:'ADZUNA_APP_ID',value:$('adzuna-id').value});await api('credentials',{name:'ADZUNA_APP_KEY',value:$('adzuna-key').value});$('adzuna-id').value='';$('adzuna-key').value='';notify('Job search credentials saved.');await refresh();});
$('account-form').onsubmit=action(async()=>{await api('account',{site:$('account-site').value,password:$('account-password').value});$('account-password').value='';notify('Account password saved.');});
$('gmail').onclick=action(async()=>{await api('gmail/connect',{});notify('Gmail sign-in opened in your browser.');});
$('settings-form').onsubmit=action(async()=>{
 const sources=JSON.parse($('sources').value);if(!Array.isArray(sources))throw Error('Job sources must be a JSON array.');
 await api('settings',{...state.settings,daily_limit:Number($('limit').value),interval_minutes:Number($('interval').value),report_hour:Number($('hour').value),timezone:$('timezone').value,model:$('model').value,review_companies:$('companies').value.split('\n').map(x=>x.trim()).filter(Boolean),sources});
 settingsLoaded=false;notify('Settings saved.');await refresh();
});
$('add-form').onsubmit=action(async event=>{await api('jobs',Object.fromEntries(new FormData(event.target)));event.target.reset();$('add-dialog').close();notify('Job added to the queue.');await refresh();});
$('resolve-form').onsubmit=action(async()=>{
 const answers=Object.fromEntries([...$('questions').querySelectorAll('textarea')].map(e=>[e.dataset.question,e.value]));
 await api(`jobs/${selected.id}/resolve`,{action:'retry',answers,confirm_not_submitted:$('not-submitted').checked});
 $('job-dialog').close();notify('Application approved and queued for the next cycle.');await refresh();
});
$('skip').onclick=action(async()=>{await api(`jobs/${selected.id}/resolve`,{action:'skip'});$('job-dialog').close();await refresh();});
$('mark-applied').onclick=()=>{$('record-evidence').value='';$('record-dialog').showModal();};
$('record-form').onsubmit=action(async()=>{await api(`jobs/${selected.id}/resolve`,{action:'applied',evidence:$('record-evidence').value});$('record-dialog').close();$('job-dialog').close();await refresh();});
refresh().catch(e=>notify(e.message,true));
setInterval(()=>refresh().catch(e=>{$('worker').textContent='Disconnected';}),5000);
