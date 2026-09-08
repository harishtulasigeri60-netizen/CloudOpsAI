(function(){
  'use strict';
  const THEME_KEY='cloudopsai-theme';
  const safe=(v)=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function applyTheme(theme){
    const t=theme==='light'?'light':'dark';
    document.documentElement.setAttribute('data-theme',t);
    document.querySelectorAll('[data-theme-icon]').forEach(x=>x.textContent=t==='light'?'☀':'☾');
    document.querySelectorAll('[data-theme-label]').forEach(x=>x.textContent=t==='light'?'Dark mode':'Light mode');
  }
  function initTheme(){
    let saved=null; try{saved=localStorage.getItem(THEME_KEY)}catch(_){ }
    applyTheme(saved==='light'?'light':'dark');
  }
  window.toggleTheme=function(){
    const next=document.documentElement.getAttribute('data-theme')==='light'?'dark':'light';
    applyTheme(next); try{localStorage.setItem(THEME_KEY,next)}catch(_){ }
  };
  window.toggleSidebar=function(){const s=document.getElementById('sidebar');if(s)s.classList.toggle('open');const o=document.getElementById('sidebarOverlay');if(o)o.classList.toggle('show');};
  window.closeSidebar=function(){const s=document.getElementById('sidebar');if(s)s.classList.remove('open');const o=document.getElementById('sidebarOverlay');if(o)o.classList.remove('show');};
  window.goBack=function(fallback){if(document.referrer && document.referrer.indexOf(location.origin)===0){history.back()}else{location.href=fallback||'/dashboard';}};
  window.refreshPage=function(){const u=new URL(location.href);u.searchParams.set('refresh','1');location.href=u.toString();};
  async function json(url){const r=await fetch(url,{headers:{Accept:'application/json', 'X-Requested-With':'XMLHttpRequest'},cache:'no-store'});if(!r.ok)throw new Error('HTTP '+r.status);return r.json();}
  function chart(id,labels,values,series){
    const el=document.getElementById(id);if(!el)return;
    const cleanSeries=(series||[{label:'CPU',values:values||[]}]).map(s=>({label:s.label||'',values:(s.values||[]).map(Number).filter(Number.isFinite)}));
    const first=cleanSeries[0]?.values||[];
    if(!first.length){el.innerHTML='<div class="chart-empty"><div><b>No telemetry available</b><br><span>CloudWatch returned no datapoints for the selected period.</span></div></div>';return;}
    const maxRaw=Math.max(...cleanSeries.flatMap(s=>s.values),1);const max=maxRaw<=100?100:Math.ceil(maxRaw/10)*10;const w=1000,h=360,p={l:62,r:24,t:24,b:46};const iw=w-p.l-p.r,ih=h-p.t-p.b;
    const n=Math.max(...cleanSeries.map(s=>s.values.length),1);const x=i=>p.l+(i/Math.max(1,n-1))*iw;const y=v=>p.t+(1-(v/max))*ih;
    const grid=[0,.25,.5,.75,1].map(q=>{const yy=p.t+q*ih;const val=Math.round(max*(1-q));return `<line x1="${p.l}" y1="${yy}" x2="${w-p.r}" y2="${yy}" stroke="currentColor" opacity=".10"/><text x="${p.l-12}" y="${yy+5}" fill="currentColor" opacity=".65" font-size="12" text-anchor="end">${val}</text>`}).join('');
    const colors=['#6575ee','#10a981','#d99a25'];
    const paths=cleanSeries.map((s,si)=>{const pts=s.values.map((v,i)=>`${i?'L':'M'} ${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(' ');return `<path d="${pts}" fill="none" stroke="${colors[si%colors.length]}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>`;}).join('');
    const area=first.map((v,i)=>`${i?'L':'M'} ${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(' ');
    const baseY=p.t+ih;const fillPath=`${area} L ${x(first.length-1).toFixed(1)} ${baseY} L ${x(0).toFixed(1)} ${baseY} Z`;
    const step=Math.max(1,Math.ceil((labels||[]).length/6));const labs=(labels||[]).map((lab,i)=>({lab,i})).filter(o=>o.i%step===0).map(o=>`<text x="${x(o.i)}" y="${h-13}" fill="currentColor" opacity=".62" font-size="11" text-anchor="middle">${safe(String(o.lab).slice(0,12))}</text>`).join('');
    const legend=cleanSeries.length>1?`<div class="chart-legend">${cleanSeries.map((s,i)=>`<span><i style="background:${colors[i%colors.length]}"></i>${safe(s.label)}</span>`).join('')}</div>`:'';
    el.innerHTML=`<div class="chart-inner">${legend}<svg class="chart-svg" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="Telemetry chart"><defs><linearGradient id="cg-${id}" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stop-color="#6575ee" stop-opacity=".24"/><stop offset="100%" stop-color="#6575ee" stop-opacity="0"/></linearGradient></defs><g>${grid}</g><path d="${fillPath}" fill="url(#cg-${id})" opacity=".7"/>${paths}${labs}</svg></div>`;
  }
  window.loadCPUChart=async function(id){if(!id){chart('cpuChart',[],[]);return}try{const d=await json('/api/cpu-history/'+encodeURIComponent(id));chart('cpuChart',d.labels||[],d.values||[])}catch(_){chart('cpuChart',[],[])} };
  window.loadMonitorCharts=async function(id){if(!id){return}try{const [c,n]=await Promise.all([json('/api/cpu-history/'+encodeURIComponent(id)),json('/api/network-history/'+encodeURIComponent(id))]);chart('monitorCpu',c.labels||[],c.values||[]);chart('networkChart',n.labels||[],n.network_in||[],[{label:'Network In',values:n.network_in||[]},{label:'Network Out',values:n.network_out||[]}])}catch(_){chart('monitorCpu',[],[]);chart('networkChart',[],[])} };
  window.loadDetailChart=async function(id){if(!id){return}try{const d=await json('/api/cpu-history/'+encodeURIComponent(id));chart('detailCpu',d.labels||[],d.values||[])}catch(_){chart('detailCpu',[],[])}};
  document.addEventListener('DOMContentLoaded',()=>{
    initTheme();
    document.querySelectorAll('.count').forEach(el=>{const t=Number(el.dataset.value);if(!Number.isFinite(t))return;const start=performance.now();function f(now){const p=Math.min(1,(now-start)/450),q=1-Math.pow(1-p,3);el.textContent=Number.isInteger(t)?Math.round(t*q):(t*q).toFixed(1);if(p<1)requestAnimationFrame(f)}requestAnimationFrame(f)});
    document.querySelectorAll('.nav').forEach(a=>a.addEventListener('click',()=>window.closeSidebar()));
    document.addEventListener('click',e=>{
      const el=e.target.closest('[data-action]'); if(!el)return;
      const action=el.dataset.action;
      if(action==='theme') window.toggleTheme();
      else if(action==='toggle-sidebar') window.toggleSidebar();
      else if(action==='close-sidebar') window.closeSidebar();
      else if(action==='back-dashboard') window.goBack('/dashboard');
      else if(action==='refresh') window.refreshPage();
      else if(action==='dismiss-toast') el.parentElement.remove();
    });
    const dash=document.getElementById('cpuChart'); if(dash?.dataset.instanceId) window.loadCPUChart(dash.dataset.instanceId);
    const detail=document.getElementById('detailCpu'); if(detail?.dataset.instanceId) window.loadDetailChart(detail.dataset.instanceId);
    const monitorButtons=[...document.querySelectorAll('.js-resource-select')];
    if(monitorButtons.length){
      const selected=monitorButtons.find(x=>x.classList.contains('active'))||monitorButtons[0];
      monitorButtons.forEach(btn=>btn.addEventListener('click',()=>{monitorButtons.forEach(x=>x.classList.remove('active'));btn.classList.add('active');window.loadMonitorCharts(btn.dataset.instanceId);}));
      if(selected?.dataset.instanceId) window.loadMonitorCharts(selected.dataset.instanceId);
    }
  });
})();
