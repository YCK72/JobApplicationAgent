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
 $('jobs').innerHTML=rows.slice(0,visibleLimit).map(j=>`<tr><td><strong>${esc(j.company)}</strong><span class="role">${esc(j.title)}</span></td><td>${esc(j.location)}</td><td><span class="badge ${j.status}">${statusNames[j.status]}</span></td><td>${esc({sde:'SDE',aiml:'AI / ML',ds:'Data Science',it:'IT / Cloud'}[j.resume]||'Pending')}</td><td>${esc(date(j.updated))}</td><td><button data-job="${j.id}" title="View application" aria-label="View application at ${esc(j.company)}">${icon('arrow-up-right')}</button></td></tr>`).join('');
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
 const missing=[!state.connections.gemini&&'Gemini',!state.connections.groq&&'Groq',!state.profile.email&&'Candidate profile',!Object.values(state.resumes).some(r=>r.enabled&&r.exists)&&'Resume'].filter(Boolean);
 $('setup-banner').hidden=!missing.length;
 $('setup-text').textContent=missing.join(' and ')+' not connected. Autopilot is paused.';
 $('key-state').textContent=state.connections.gemini?'Gemini key saved':'No Gemini key saved'; $('groq-state').textContent=state.connections.groq?'Groq key saved':'No Groq key saved';
 $('gmail-state').textContent=state.connections.gmail?'Gmail authorized':state.connections.gmail_client?'OAuth client ready. Connect your Gmail account.':'OAuth client missing: secrets/gmail-client.json';
 $('adzuna-state').textContent=state.connections.adzuna?'Credentials saved':'Not configured';
 const labels={name:'Name',email:'Email',phone:'Phone',location:'Location',linkedin:'LinkedIn',github:'GitHub',work_authorization:'Work authorization',preferences:'Preferences'};
 $('profile-values').innerHTML=Object.entries(labels).map(([key,label])=>`<dt>${label}</dt><dd>${esc(state.profile[key]||'Not provided')}</dd>`).join('');
 $('resumes').innerHTML=Object.entries(state.resumes).map(([key,r])=>`<div class="resume">${icon('file-text')}<div><strong>${esc(r.role)}</strong><p>${r.exists?(r.enabled?'Available for applications':r.placeholder?'Placeholder - replace before applying':'Reference document'):'File missing'}</p></div></div>`).join('');
 $('events').innerHTML=state.events.map(e=>`<div class="event"><time>${esc(date(e.created))}</time><span>${esc(e.message)}</span></div>`).join('')||'<p>No activity recorded.</p>';
 $('deliveries').innerHTML=state.reports.map(r=>`<div class="event"><time>${esc(r.day)}</time><span>${esc(r.status==='sending'?'Delivery pending confirmation':r.status)}</span></div>`).join('')||'<p>No reports sent.</p>';
 if(!settingsLoaded){
  $('profile-json').value=JSON.stringify(state.profile.answers||{},null,2);
  const fields={name:'Full name',first_name:'First name',last_name:'Last name',email:'Email address',phone:'Phone number',city:'City',location:'Current location',country:'Country',linkedin:'LinkedIn URL',github:'GitHub URL',work_authorization:'Work authorization',preferences:'Job preferences'};
  const choices={authorized_to_work_us:'Currently authorized to work in the US',requires_sponsorship:'Future sponsorship required',willing_to_relocate:'Willing to relocate'};
  $('profile-inputs').innerHTML=Object.entries(fields).map(([key,label])=>`<label>${esc(label)}<input data-profile="${key}" value="${esc(state.profile[key]||'')}" ${['name','email'].includes(key)?'required':''}></label>`).join('')+Object.entries(choices).map(([key,label])=>`<label>${esc(label)}<select data-profile="${key}"><option value="">Not specified</option><option value="true" ${state.profile[key]===true?'selected':''}>Yes</option><option value="false" ${state.profile[key]===false?'selected':''}>No</option></select></label>`).join('');
  $('handoff').checked=state.settings.interactive_handoff; $('handoff-timeout').value=state.settings.handoff_timeout_seconds;
  $('tailor').checked=state.settings.tailor_resumes; $('review-tech').checked=state.settings.review_large_tech;
  $('limit').value=state.settings.daily_limit;$('interval').value=state.settings.interval_minutes;$('hour').value=state.settings.report_hour;
  $('timezone').value=state.settings.timezone;$('model').value=state.settings.gemini_model;$('groq-model').value=state.settings.groq_model;
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
 $('job-detail').innerHTML=`<span class="badge ${j.status}">${statusNames[j.status]}</span><p>${esc(j.reason||'Awaiting evaluation')}</p><p>${esc(j.location)} &nbsp; <a href="${esc(safeUrl)}" target="_blank" rel="noreferrer">Open posting</a>${j.tailored_resume?` &nbsp; <a href="/api/resumes/${j.id}" target="_blank" rel="noreferrer">Prepared resume</a>`:''}${j.evidence?` &nbsp; <a href="/api/evidence/${j.id}" target="_blank" rel="noreferrer">View screenshot</a>`:''}</p><details><summary>Job description</summary><p class="description">${esc(j.description)}</p></details>`;
 const questions=JSON.parse(j.questions||'[]');
 $('questions').innerHTML=questions.map((q,i)=>`<label>${esc(q)}<textarea data-question="${esc(q)}" rows="2"></textarea></label>`).join('');
 $('resolve-form').hidden=!['needs_review','skipped'].includes(j.status);
 $('retry-confirm').hidden=!j.attempted;$('not-submitted').checked=false; $('remember-answers').checked=false;
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
$('key-form').onsubmit=action(async()=>{await api('credentials',{name:'GEMINI_API_KEY',value:$('api-key').value});$('api-key').value='';notify('API key saved in your system credential vault.');await refresh();});
$('groq-form').onsubmit=action(async()=>{await api('credentials',{name:'GROQ_API_KEY',value:$('groq-key').value});$('groq-key').value='';notify('Groq key saved.');await refresh();});
 $('adzuna-form').onsubmit=action(async()=>{await api('credentials',{name:'ADZUNA_APP_ID',value:$('adzuna-id').value});await api('credentials',{name:'ADZUNA_APP_KEY',value:$('adzuna-key').value});$('adzuna-id').value='';$('adzuna-key').value='';notify('Job search credentials saved.');await refresh();});
$('account-form').onsubmit=action(async()=>{await api('account',{site:$('account-site').value,password:$('account-password').value});$('account-password').value='';notify('Account password saved.');});
$('gmail').onclick=action(async()=>{await api('gmail/connect',{});notify('Gmail sign-in opened in your browser.');});
$('settings-form').onsubmit=action(async()=>{
 const sources=JSON.parse($('sources').value);if(!Array.isArray(sources))throw Error('Job sources must be a JSON array.');
 await api('settings',{...state.settings,interactive_handoff:$('handoff').checked,handoff_timeout_seconds:Number($('handoff-timeout').value),tailor_resumes:$('tailor').checked,review_large_tech:$('review-tech').checked,daily_limit:Number($('limit').value),interval_minutes:Number($('interval').value),report_hour:Number($('hour').value),timezone:$('timezone').value,gemini_model:$('model').value,groq_model:$('groq-model').value,review_companies:$('companies').value.split('\n').map(x=>x.trim()).filter(Boolean),sources});
 settingsLoaded=false;notify('Settings saved.');await refresh();
});
$('add-form').onsubmit=action(async event=>{await api('jobs',Object.fromEntries(new FormData(event.target)));event.target.reset();$('add-dialog').close();notify('Job added to the queue.');await refresh();});
$('resolve-form').onsubmit=action(async()=>{
 const answers=Object.fromEntries([...$('questions').querySelectorAll('textarea')].map(e=>[e.dataset.question,e.value]));
 await api(`jobs/${selected.id}/resolve`,{action:'retry',answers,remember_answers:$('remember-answers').checked,confirm_not_submitted:$('not-submitted').checked});
 $('job-dialog').close();notify('Application approved and queued for the next cycle.');await refresh();
});
$('skip').onclick=action(async()=>{await api(`jobs/${selected.id}/resolve`,{action:'skip'});$('job-dialog').close();await refresh();});
$('mark-applied').onclick=()=>{$('record-evidence').value='';$('record-dialog').showModal();};
$('record-form').onsubmit=action(async()=>{await api(`jobs/${selected.id}/resolve`,{action:'applied',evidence:$('record-evidence').value});$('record-dialog').close();$('job-dialog').close();await refresh();});
refresh().catch(e=>notify(e.message,true));
$('profile-form').onsubmit=action(async()=>{const fields=Object.fromEntries([...$('profile-inputs').querySelectorAll('[data-profile]')].map(el=>[el.dataset.profile,el.tagName==='SELECT'?(el.value===''?null:el.value==='true'):el.value])); const answers=JSON.parse($('profile-json').value); await api('profile',{...state.profile,...fields,answers});notify('Candidate facts and reusable answers saved.');await refresh();});
$('resume-form').onsubmit=action(async()=>{
 const file=$('resume-file').files[0];if(!file||file.size>10000000)throw Error('Choose a PDF under 10 MB.');
 const content=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onerror=reject;reader.onload=()=>resolve(reader.result.split(',')[1]);reader.readAsDataURL(file);});
 await api('resumes',{kind:$('resume-kind').value,content});notify('Resume imported.');$('resume-form').reset();await refresh();
});
setInterval(()=>refresh().catch(e=>{$('worker').textContent='Disconnected';}),5000);

$('apify-form').onsubmit=action(async()=>{await api('credentials',{name:'APIFY_TOKEN',value:$('apify-token').value});$('apify-token').value='';notify('Apify token saved in your system credential vault.');});

$('mfa-form').onsubmit=action(async()=>{await api('mfa',{site:$('mfa-site').value,seed:$('mfa-seed').value});$('mfa-seed').value='';notify('Authenticator seed saved in your system credential vault.');});
