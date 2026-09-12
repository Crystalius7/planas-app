/* board.js - the handwritten maths board (owner 2026-09-10: "interactive step by step animations ... handwritten lithuanian
   style ... explanation in words what's been done in that step and why and best way to mentally calculate").
   Inlined by tools/topic.py (topic pages) and tools/plan.py (the hub). Content contract + validator: tools/topic.py.

   A board is a list of STEPS. Each step writes zero or more LINES in ink, then draws MARKS in red pen, then explains:
     {"w": "line" | ["line", ...], "marks": [["o"|"x"|"u"|"b", "<id>", "note?", "g?"]],
      "do": "Ka darau", "why": "Kodel", "mind": "Mintyse - greiciausias budas", "ask": {"q": "...", "o": ["..."], "r": 0},
      "calc": {"k": ["6","2","5","pow","3","÷","4","▶","="], "d": "125", "n": "note?"}}   (keys: tools/calc.py, verified at build)
   LINE markup: ^{..} / ^2 / ^-2 powers, _{..} indices, \f{a}{b} fraction, √{..} or √[3]{..} root, [#id ..] a part a later
   mark can circle (o), cross out (x), underline (u) or box (b); a line starting with "~" is words (wraps); "Ats." lines get
   the double underline a teacher expects. Unicode powers (x⁻²) and ∪ ∩ ∈ ∉ ∞ → ⇒ ∅ are drawn by hand (fonts lack them).
   Learning mechanics: prediction before a step (ask), backward fading by level (0 watch, 1 finish the last half yourself,
   2 whole task yourself), a hint ladder on your own steps, skip-to-final for reduced motion. */
(function(){
'use strict';
if(window.Board)return;
const reduced=()=>!!(window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches);
const esc=s=>String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const SUP={'⁰':'0','¹':'1','²':'2','³':'3','⁴':'4','⁵':'5','⁶':'6','⁷':'7','⁸':'8','⁹':'9','⁻':'-','⁺':'+','ⁿ':'n','ˣ':'x'};
const SUB={'₀':'0','₁':'1','₂':'2','₃':'3','₄':'4','₅':'5','₆':'6','₇':'7','₈':'8','₉':'9','ₐ':'a','ₓ':'x'};
const GL={
  '∪':'M4 4 C4 18 16 18 16 4','∩':'M4 18 C4 4 16 4 16 18',
  '∈':'M16 5 C7 4 4 8 4 11 C4 14 7 18 16 17 M5 11 H14','∉':'M16 5 C7 4 4 8 4 11 C4 14 7 18 16 17 M5 11 H14 M13 1.5 L7 20.5',
  '∞':'M10 11 C7.5 6 2 7 2 11 C2 15 7.5 16 10 11 C12.5 6 18 7 18 11 C18 15 12.5 16 10 11',
  '→':'M2 11 H17 M12 6.5 L17 11 L12 15.5','⇒':'M2 8.5 H15 M2 13.5 H15 M11 4.5 L17.5 11 L11 17.5',
  '∅':'M10 4 C4.5 4 3 8.5 3 11 C3 15 6 18 10 18 C14.5 18 17 14.5 17 11 C17 7 14.5 4 10 4 M16.5 2 L3.5 20',
  '⊂':'M17 5 C6 4 3.5 8 3.5 11 C3.5 14 6 18 17 17'};
const ROOT_PATH='M0.5 14 L3 12.6 L6 22.6 L9.6 1';
const PEN='<svg class="bd-pen" viewBox="0 0 32 32" aria-hidden="true"><path d="M5 27 L8.5 19.5 L23.5 4.5 L27.5 8.5 L12.5 23.5 Z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M5 27 L8.5 19.5 L12.5 23.5 Z" fill="currentColor"/></svg>';

/* ---------- markup -> html ---------- */
function md(src,words){
  const s=String(src);let i=0;
  const glyph=ch=>`<svg class="bd-g" viewBox="0 0 20 22" aria-hidden="true"><path d="${GL[ch]}"/></svg><span class="bd-sr">${ch}</span>`;
  const emit=ch=>GL[ch]?glyph(ch):(ch==='-'&&!words)?'−':esc(ch);
  // the radicand sits in an inline .bd-rbi INSIDE the flex box .bd-rb (glance 2026-09-12: a power that is a direct flex child
  // ignores vertical-align and would print √3² as "32")
  const root=(n,a)=>`<span class="bd-rt">${n?`<span class="bd-ri">${n}</span>`:''}<svg viewBox="0 0 10 24" preserveAspectRatio="none" aria-hidden="true"><path d="${ROOT_PATH}"/></svg><span class="bd-rb"><span class="bd-rbi">${a}</span></span></span>`;
  function arg(script){
    if(s[i]==='{'){i++;return seq('}');}
    if(s[i]==='('&&!script){let d=0,j=i;for(;j<s.length;j++){if(s[j]==='(')d++;else if(s[j]===')'&&--d===0)break;}const inner=s.slice(i+1,j);i=j+1;return md(inner,words);}
    const m=/^[-−]?(?:\d+(?:,\d+)?|[A-Za-zα-ωπ])/.exec(s.slice(i));
    if(m){i+=m[0].length;return m[0].split('').map(emit).join('');}
    const ch=s[i++]||'';return emit(ch);
  }
  function seq(stop){
    let h='';
    while(i<s.length){
      const ch=s[i];
      if(stop&&ch===stop){i++;return h;}
      if(ch==='\\'&&s[i+1]==='f'&&s[i+2]==='{'){i+=2;const a=arg(),b=arg();h+=`<span class="bd-fr"><span class="bd-nu">${a}</span><span class="bd-de">${b}</span></span>`;continue;}
      if(ch==='\\'&&s[i+1]==='r'&&(s[i+2]==='{'||s[i+2]==='[')){i+=2;let n='';if(s[i]==='['){i++;n=seq(']');}h+=root(n,arg());continue;}
      if(ch==='√'){i++;let n='';if(s[i]==='['){i++;n=seq(']');}h+=root(n,arg());continue;}
      if((ch==='^'||ch==='_')&&i+1<s.length){i++;const a=arg(true);h+=ch==='^'?`<sup>${a}</sup>`:`<sub>${a}</sub>`;continue;}
      if(ch==='['&&s[i+1]==='#'){const m=/^\[#([\w-]+) ?/.exec(s.slice(i));if(m){i+=m[0].length;h+=`<span class="bd-id" data-id="${m[1]}">${seq(']')}</span>`;continue;}}
      if(SUP[ch]){let r='';while(i<s.length&&SUP[s[i]])r+=SUP[s[i++]];h+=`<sup>${r.split('').map(emit).join('')}</sup>`;continue;}
      if(SUB[ch]){let r='';while(i<s.length&&SUB[s[i]])r+=SUB[s[i++]];h+=`<sub>${esc(r)}</sub>`;continue;}
      h+=emit(ch);i++;
    }
    return h;
  }
  return seq(null);
}
/* explanation text: plain HTML with $math$ segments in the same hand as the board */
const say=t=>String(t||'').replace(/\$([^$]+)\$/g,(m,x)=>`<span class="bd-im">${md(x)}</span>`);
/* calculator strip (owner 2026-09-12: "guide me what to press on scientific calculator"): abstract key tokens rendered with
   the owner's calculator family from tools/calc.py (KEYMAP inlined by topic.py); tapping the strip lights the keys in order. */
const KEYMAP=/*__KEYMAP__*/null;
function keyHtml(t){const km=KEYMAP&&KEYMAP.keys[t];if(!km)return `<kbd class="ck">${esc(t)}</kbd>`;const hint=km[2]?` title="${esc(km[2])}"`:'';
  if(km[1])return `<kbd class="ck ck-s">SHIFT</kbd><kbd class="ck"${hint}>${esc(km[0])}<i>${esc(km[1])}</i></kbd>`;
  return `<kbd class="ck${(t==='▶'||t==='▼')?' ck-a':''}"${hint}>${esc(km[0])}</kbd>`;}
/* owner 2026-09-12 (second note): "each step must be shown as a button i have to press on calculator, one by one, without rushing or
   skipping anything" - no timer: the strip is a STEPPER the owner advances himself; every key (SHIFT included) is one step. */
const CT={lt:{go:'Po vieną klavišą ▶',press:'Spausk',next:'Kitas klavišas →',again:'Iš naujo',disp:'Ekrane:',of:'iš',title:'Klavišai po vieną – tu pats spaudi „Kitas“'},
          en:{go:'One key at a time ▶',press:'Press',next:'Next key →',again:'Start again',disp:'Display:',of:'of',title:'One key at a time – you press "Next" yourself'}};
function calcHtml(c,lang){if(!c||!Array.isArray(c.k))return '';const en=lang==='en',t=CT[en?'en':'lt'];
  return `<div class="bd-calc" data-calc="1" data-lang="${en?'en':'lt'}" title="${t.title}"><b>🔢 ${en?'On the calculator.':'Skaičiuotuve.'}</b> <span class="ckeys">${c.k.map(keyHtml).join('')}</span><span class="cd">→ ${esc(c.d)}</span>${c.n?`<span class="cn">${esc(c.n)}</span>`:''}`+
    `<div class="cstep"><button type="button" class="cs-go">${t.go}</button><span class="cs-now" hidden><span class="cs-i"></span> <span class="cs-say">${t.press}</span> <span class="cs-k"></span></span><button type="button" class="cs-next" hidden>${t.next}</button><button type="button" class="cs-reset" hidden>${t.again}</button></div></div>`;}
function stepCalc(el,target){const t=CT[el.dataset.lang==='en'?'en':'lt'];const keys=[...el.querySelectorAll('.ckeys .ck')];
  const q=s=>el.querySelector(s);const go=q('.cs-go'),now=q('.cs-now'),nxt=q('.cs-next'),rst=q('.cs-reset'),ki=q('.cs-i'),ks=q('.cs-say'),kk=q('.cs-k');
  if(!keys.length||!go)return;
  const reset=()=>{keys.forEach(k=>k.classList.remove('lit','done'));el._i=undefined;go.hidden=false;now.hidden=true;nxt.hidden=true;rst.hidden=true;};
  if(target&&target.closest&&target.closest('.cs-reset')){reset();go.focus();return;}
  const i=el._i==null?0:el._i+1;el._i=i;
  keys.forEach((k,j)=>{k.classList.toggle('done',j<i);k.classList.toggle('lit',j===i);});
  go.hidden=true;now.hidden=false;rst.hidden=false;
  if(i<keys.length){ki.textContent=`${i+1} ${t.of} ${keys.length}`;ks.textContent=t.press;kk.innerHTML=keys[i].outerHTML.replace(/ class="ck/,' class="ck big');nxt.hidden=false;nxt.focus({preventScroll:true});}
  else{ki.textContent='✓';ks.textContent=t.disp;kk.innerHTML=`<span class="cd">${esc((q('.cd')||{}).textContent||'')}</span>`;nxt.hidden=true;rst.focus({preventScroll:true});}}
const playCalc=stepCalc;   // the hub calls this name: a tap anywhere on the strip is one step forward, never a timed replay
function wireCalc(scope){scope.querySelectorAll('[data-calc]').forEach(el=>{el.onclick=e=>{e.stopPropagation();stepCalc(el,e.target);};el.onkeydown=e=>{if((e.key==='Enter'||e.key===' ')&&!e.target.closest('button')){e.preventDefault();stepCalc(el,e.target);}};});}
function lineEl(src){
  const words=/^~/.test(src),body=words?src.replace(/^~\s?/,''):src;
  const el=document.createElement('div');
  el.className='bd-l'+(words?' bd-txt':'');
  if(/^\s*Ats\./.test(body))el.dataset.ans='1';
  el.innerHTML=`<span class="bd-in">${md(body,words)}</span>`;
  return el;
}
const linesOf=st=>st.w==null?[]:(Array.isArray(st.w)?st.w:[st.w]);

/* ---------- drawing helpers shared by both players ---------- */
function Sheet(root){
  const paper=document.createElement('div');paper.className='bd-paper';
  const sheet=document.createElement('div');sheet.className='bd-sheet';
  sheet.innerHTML=`<svg class="bd-ov" aria-hidden="true"></svg><div class="bd-lines"></div><div class="bd-notes"></div>${PEN}`;
  paper.appendChild(sheet);root.appendChild(paper);
  const ov=sheet.querySelector('.bd-ov'),lines=sheet.querySelector('.bd-lines'),notes=sheet.querySelector('.bd-notes'),pen=sheet.querySelector('.bd-pen');
  let anims=[];
  const S={sheet,lines,
    clear(){lines.innerHTML='';notes.innerHTML='';ov.innerHTML='';},
    fit(){ov.setAttribute('width',sheet.scrollWidth);ov.setAttribute('height',sheet.scrollHeight);ov.setAttribute('viewBox',`0 0 ${sheet.scrollWidth} ${sheet.scrollHeight}`);},
    rel(el){const a=sheet.getBoundingClientRect(),r=el.getBoundingClientRect();return {x:r.left-a.left,y:r.top-a.top,w:r.width,h:r.height};},
    finish(){anims.forEach(a=>{try{a.finish();}catch(e){}});anims=[];},
    busy(){return anims.some(a=>a.playState==='running'||a.playState==='pending');},
    write(el,speed){
      if(reduced()||!speed||!el.animate)return Promise.resolve();
      const n=Math.max(1,el.textContent.replace(/\s+/g,'').length),dur=Math.max(420,Math.min(2600,n*70))/speed;
      const a=el.animate([{clipPath:'inset(-6px 100% -6px -6px)'},{clipPath:'inset(-6px -6px -6px -6px)'}],{duration:dur,easing:'linear',fill:'backwards'});
      const b=S.rel(el.querySelector('.bd-in')||el),kf=[];
      for(let q=0;q<=12;q++)kf.push({opacity:q===12?0:1,transform:`translate(${(b.x+b.w*q/12-5).toFixed(1)}px,${(b.y+b.h-24+(q%2?-3:2)).toFixed(1)}px)`});
      const p=pen.animate(kf,{duration:dur,easing:'linear'});
      anims.push(a,p);
      return a.finished.then(()=>{},()=>{});
    },
    mark(m,speed,upto){
      const [type,id,note,col]=m;
      const stepOf=e=>{const l=e.closest('.bd-l');return l?+l.dataset.step:0;};
      const targets=[...sheet.querySelectorAll('.bd-id')].filter(e=>e.dataset.id===id&&(upto==null||stepOf(e)<=upto));
      if(!targets.length)return Promise.resolve();
      const b=S.rel(targets[targets.length-1]);S.fit();
      const d=path(type,b);
      const ns='http://www.w3.org/2000/svg',el=document.createElementNS(ns,'path');
      el.setAttribute('d',d);if(col==='g')el.setAttribute('class','g');ov.appendChild(el);
      if(note){const t=document.createElement('div');t.className='bd-note'+(col==='g'?' g':'');t.innerHTML=md(note);
        const lift=type==='o'?31:23,above=b.y>lift;t.style.left=(b.x+b.w/2)+'px';t.style.top=(above?b.y-lift:b.y+b.h+(type==='o'?10:4))+'px';notes.appendChild(t);
        if(speed&&!reduced()&&t.animate)anims.push(t.animate([{opacity:0,transform:'translateX(-50%) translateY(4px)'},{opacity:1,transform:'translateX(-50%)'}],{duration:320/speed,delay:260/speed,fill:'backwards'}));}
      if(!speed||reduced()||!el.animate)return Promise.resolve();
      const L=el.getTotalLength();el.style.strokeDasharray=L+' '+L;
      const a=el.animate([{strokeDashoffset:L},{strokeDashoffset:0}],{duration:460/speed,easing:'ease-out',fill:'both'});
      anims.push(a);
      return a.finished.then(()=>{},()=>{});
    },
    ansLine(el,speed){const b=S.rel(el.querySelector('.bd-in')||el);return S.markBox(`M${b.x-3} ${b.y+b.h+3} Q${b.x+b.w/2} ${b.y+b.h+6} ${b.x+b.w+4} ${b.y+b.h+2} M${b.x-1} ${b.y+b.h+8} Q${b.x+b.w/2} ${b.y+b.h+11} ${b.x+b.w+2} ${b.y+b.h+7}`,speed);},
    markBox(d,speed){S.fit();const el=document.createElementNS('http://www.w3.org/2000/svg','path');el.setAttribute('d',d);ov.appendChild(el);
      if(!speed||reduced()||!el.animate)return Promise.resolve();const L=el.getTotalLength();el.style.strokeDasharray=L+' '+L;
      const a=el.animate([{strokeDashoffset:L},{strokeDashoffset:0}],{duration:420/speed,easing:'ease-out',fill:'both'});anims.push(a);return a.finished.then(()=>{},()=>{});}
  };
  return S;
}
function path(type,b){
  const {x,y,w,h}=b;
  if(type==='o'){const cx=x+w/2,cy=y+h/2,rx=w/2+9,ry=h/2+6;let d='';
    for(let q=0;q<=32;q++){const a=-2.3+q*(2*Math.PI+0.55)/32,k=1+0.035*Math.sin(q*1.9);d+=(q?'L':'M')+(cx+rx*k*Math.cos(a)).toFixed(1)+' '+(cy+ry*k*Math.sin(a)).toFixed(1)+' ';}
    return d;}
  if(type==='x')return `M${x-3} ${y+h*.8} Q${x+w*.5} ${y+h*.56} ${x+w+3} ${y+h*.18}`;
  if(type==='u')return `M${x-2} ${y+h+2} Q${x+w*.5} ${y+h+6} ${x+w+3} ${y+h+1}`;
  return `M${x-6} ${y-3} L${x+w+6} ${y-4.5} L${x+w+5} ${y+h+4} L${x-5.5} ${y+h+3} Z`;
}
function whenFonts(){
  if(!document.fonts||!document.fonts.load)return Promise.resolve();
  return Promise.race([Promise.all([document.fonts.load('600 31px Caveat'),document.fonts.load('600 15px "Shantell Sans"')]).catch(()=>{}),new Promise(r=>setTimeout(r,1500))]);
}

/* ---------- the worked-solution player ---------- */
function mount(root,steps,opt){
  if(!root||!Array.isArray(steps)||!steps.length||root.dataset.bdOn)return;
  opt=opt||{};root.dataset.bdOn='1';root.classList.add('bd');root.innerHTML='';
  root.addEventListener('click',e=>e.stopPropagation());
  root.addEventListener('keydown',e=>e.stopPropagation());
  const n=steps.length,S=Sheet(root);
  const askEl=document.createElement('div');askEl.className='bd-ask';askEl.hidden=true;root.appendChild(askEl);
  const sayEl=document.createElement('div');sayEl.className='bd-say';sayEl.setAttribute('aria-live','polite');root.appendChild(sayEl);
  const ctl=document.createElement('div');ctl.className='bd-ctl';
  const MODES=['Žiūriu','Užbaigiu pats','Sprendžiu pats'];
  ctl.innerHTML=`<button class="bd-b" data-a="back" aria-label="Žingsnis atgal">◀</button><button class="bd-b pri" data-a="next"></button><button class="bd-b" data-a="all">Visas sprendimas ⏭</button>`+
    `<div class="bd-modes" role="group" aria-label="Kiek darai pats">${MODES.map((t,j)=>`<button class="bd-b bd-m" data-m="${j}" aria-pressed="false">${t}</button>`).join('')}</div>`;
  root.appendChild(ctl);
  const dots=document.createElement('div');dots.className='bd-dots';
  dots.innerHTML=steps.map((s,j)=>`<button class="bd-dot" data-d="${j}" aria-label="Žingsnis ${j+1}">${j+1}</button>`).join('');
  root.appendChild(dots);
  const bNext=ctl.querySelector('[data-a="next"]'),bBack=ctl.querySelector('[data-a="back"]');
  let level=Math.max(0,Math.min(2,opt.level|0)),k=0,pending=-1,run=0,revealed={},asked={};
  const hideFrom=()=>level===0?n:level===2?Math.min(1,n-1):Math.max(1,n-Math.ceil((n-1)/2));
  const mine=j=>j>=hideFrom()&&!revealed[j];

  function explain(j){
    if(j<0){sayEl.innerHTML=`<div class="bd-k">Sprendimas ranka · ${n} žingsn.</div><p>${level===2?'Pirma išspręsk visą užduotį ant lapo, tik tada tikrinkis.':level===1?'Pradžią parodysiu, paskutinius žingsnius parašysi pats.':'Spausk „Pradėti“ – sprendimas rašomas ranka po vieną žingsnį: ką darau, kodėl ir kaip greičiausiai suskaičiuoti mintyse.'}</p>`;return;}
    const s=steps[j];
    sayEl.innerHTML=`<div class="bd-k">Žingsnis ${j+1} iš ${n}</div>${s.do?`<p><b>Ką darau.</b> ${say(s.do)}</p>`:''}${s.why?`<p><b>Kodėl.</b> ${say(s.why)}</p>`:''}${s.mind?`<p class="bd-mind"><b>🧠 Mintyse.</b> ${say(s.mind)}</p>`:''}${s.calc?calcHtml(s.calc):''}`;
    wireCalc(sayEl);
  }
  function yourTurn(j){
    const s=steps[j],solo=level===2;
    const el=document.createElement('div');el.className='bd-l bd-blank';el.dataset.blank='1';
    el.textContent=solo?'✎ Tavo sprendimas – parašyk jį visą ant lapo':'✎ Tavo eilė – parašyk šį žingsnį ant lapo';
    S.lines.appendChild(el);
    sayEl.innerHTML=`<div class="bd-k">${solo?'Visa užduotis – tavo':'Žingsnis '+(j+1)+' iš '+n+' – tavo eilė'}</div><p>${solo?'Išspręsk iki atsakymo, tada spausk „Tikrinti“ ir žiūrėk, kur sutampa.':'Pirma parašyk pats, tada spausk „Tikrinti“.'}</p>`+
      (s.do&&!solo?`<p><button class="bd-b" data-hint="1">Užuomina</button></p>`:'');
    const h=sayEl.querySelector('[data-hint]');if(h)h.onclick=()=>{h.parentNode.innerHTML=`<b>Užuomina.</b> ${say(s.do)}`;};
  }
  function label(){
    dots.querySelectorAll('.bd-dot').forEach((d,j)=>{d.classList.toggle('on',j<k);d.classList.toggle('cur',j===k-1);d.classList.toggle('me',j>=hideFrom());});
    ctl.querySelectorAll('.bd-m').forEach((b,j)=>b.setAttribute('aria-pressed',String(j===level)));
    bBack.disabled=k===0&&pending<0;bNext.disabled=false;
    if(pending>=0)bNext.textContent='Tikrinti ✓';
    else if(k===0)bNext.textContent=level===2?'Pradėti ▶':'Pradėti ▶';
    else if(k>=n)bNext.textContent='Iš naujo ⟲';
    else bNext.textContent=mine(k)?'Mano eilė ✎':'Kitas žingsnis ▶';
  }
  function drawStatic(upto){
    S.finish();run++;askEl.hidden=true;S.clear();
    for(let j=0;j<upto;j++)addLines(j);
    S.fit();
    for(let j=0;j<upto;j++){(steps[j].marks||[]).forEach(m=>S.mark(m,0,j));S.lines.querySelectorAll(`[data-step="${j}"][data-ans]`).forEach(el=>S.ansLine(el,0));}
    k=upto;
    if(pending>=0)yourTurn(pending);else explain(upto-1);
    label();
  }
  function addLines(j){
    const out=[];
    if(steps[j].svg){const f=document.createElement('div');f.className='bd-l bd-fig';f.dataset.step=j;f.innerHTML=steps[j].svg;S.lines.appendChild(f);out.push(f);}
    linesOf(steps[j]).forEach((src,li)=>{const el=lineEl(src);el.dataset.step=j;
      if(li===0){const num=document.createElement('span');num.className='bd-num';num.textContent=(j+1)+')';el.appendChild(num);}
      S.lines.appendChild(el);out.push(el);});
    return out;
  }
  async function play(j,speed){
    const my=++run;askEl.hidden=true;
    const blank=S.lines.querySelector('[data-blank]');if(blank)blank.remove();
    k=j+1;label();
    const els=addLines(j);S.fit();
    for(const el of els){await S.write(el,speed);if(my!==run)return;}
    for(const m of (steps[j].marks||[])){await S.mark(m,speed,j);if(my!==run)return;}
    for(const el of els)if(el.dataset.ans){await S.ansLine(el,speed);if(my!==run)return;}
    explain(j);label();
  }
  function ask(j){
    const q=steps[j].ask;asked[j]=true;askEl.hidden=false;
    askEl.innerHTML=`<div class="bd-k">Spėk prieš žiūrėdamas</div><p>${say(q.q||'Koks kitas žingsnis?')}</p>${q.o.map((o,i)=>`<button class="bd-o" data-o="${i}">${say(o)}</button>`).join('')}<p><button class="bd-b" data-o="skip">Praleisti</button></p>`;
    bNext.disabled=true;
    askEl.onclick=e=>{const b=e.target.closest('[data-o]');if(!b)return;
      if(b.dataset.o==='skip'){bNext.disabled=false;play(j,1);return;}
      const i=+b.dataset.o,ok=i===q.r;
      askEl.querySelectorAll('.bd-o').forEach((x,xi)=>{x.disabled=true;if(xi===q.r)x.classList.add('ok');else if(xi===i)x.classList.add('no');});
      const fb=document.createElement('p');fb.innerHTML=ok?'<b>Taip!</b> Žiūrėk, kaip tai atrodo ant lapo.':'<b>Ne visai</b> – teisingas pažymėtas žaliai. Žiūrėk, kodėl.';askEl.appendChild(fb);
      setTimeout(()=>{bNext.disabled=false;play(j,1);},ok?900:1900);};
  }
  function next(){
    if(S.busy()){S.finish();return;}
    if(pending>=0){const j=pending;pending=-1;if(level===2){for(let x=j;x<n;x++)revealed[x]=true;playFrom(j);}else{revealed[j]=true;play(j,1);}return;}
    if(k>=n){reset();return;}
    const j=k;
    if(mine(j)){pending=j;yourTurn(j);label();return;}
    if(steps[j].ask&&!asked[j]){ask(j);return;}   // any watched step predicts first (round 6)
    play(j,1);
  }
  async function playFrom(j){const my=run+1;for(let x=j;x<n;x++){await play(x,2.2);if(run!==my+(x-j))return;}}
  function reset(){pending=-1;revealed={};asked={};drawStatic(0);explain(-1);label();}
  bNext.onclick=next;
  bBack.onclick=()=>{if(pending>=0){pending=-1;drawStatic(k);return;}if(k>0){drawStatic(k-1);}};
  ctl.querySelector('[data-a="all"]').onclick=()=>{pending=-1;for(let x=0;x<n;x++)revealed[x]=true;drawStatic(n);};
  ctl.querySelectorAll('.bd-m').forEach(b=>b.onclick=()=>{level=+b.dataset.m;reset();if(opt.onLevel)opt.onLevel(level);});
  dots.onclick=e=>{const d=e.target.closest('[data-d]');if(!d)return;const j=+d.dataset.d;pending=-1;for(let x=0;x<=j;x++)revealed[x]=true;drawStatic(j+1);};
  let rt=0;window.addEventListener('resize',()=>{clearTimeout(rt);rt=setTimeout(()=>{if(root.isConnected&&!S.busy()&&k>0)drawStatic(k);},200);});
  explain(-1);label();
  whenFonts().then(()=>{if(opt.autoplay!==false&&level<2&&k===0)play(0,1);else if(k===0&&level===2){play(0,0).then(()=>{pending=1<n?1:-1;if(pending>=0)yourTurn(1);label();});}});
}

/* ---------- "Rask klaidą": an erroneous worked example (Große & Renkl 2007) ---------- */
function mistake(root,item,opt){
  if(!root||!item||!Array.isArray(item.board)||root.dataset.bdOn)return;
  opt=opt||{};root.dataset.bdOn='1';root.classList.add('bd');root.innerHTML='';
  root.addEventListener('click',e=>e.stopPropagation());
  const S=Sheet(root);
  const sayEl=document.createElement('div');sayEl.className='bd-say';sayEl.setAttribute('aria-live','polite');root.appendChild(sayEl);
  let tries=0,done=false;
  sayEl.innerHTML=`<div class="bd-k">Rask klaidą</div><p>Vienas žingsnis neteisingas. Spausk eilutę, kurioje suklysta – turi vieną bandymą.</p>`;
  function draw(){
    S.clear();
    item.board.forEach((st,j)=>linesOf(st).forEach((src,li)=>{const el=lineEl(src);el.dataset.step=j;
      if(j>0&&!done){el.classList.add('bd-click');el.tabIndex=0;el.setAttribute('role','button');}
      if(li===0){const num=document.createElement('span');num.className='bd-num';num.textContent=(j+1)+')';el.appendChild(num);}
      S.lines.appendChild(el);}));
    S.fit();
  }
  async function reveal(ok){
    done=true;S.sheet.querySelector('.bd-notes').innerHTML='';S.lines.querySelectorAll('.bd-click').forEach(el=>{el.classList.remove('bd-click');el.removeAttribute('tabindex');el.removeAttribute('role');});
    // reviewer 2026-09-10: everything that followed from the error is wrong too - dim it, strike the bad step, and write the
    // corrected continuation in green through to its own Ats.: so the last answer on the paper is the right one
    [...S.lines.querySelectorAll('.bd-l')].filter(el=>+el.dataset.step>=item.bad).forEach(el=>{el.classList.add('bd-wrong');
      if(+el.dataset.step===item.bad){el.classList.add('bd-bad');const b=S.rel(el.querySelector('.bd-in'));S.markBox(`M${b.x-3} ${b.y+b.h*.72} Q${b.x+b.w/2} ${b.y+b.h*.5} ${b.x+b.w+3} ${b.y+b.h*.25}`,1);}});
    const fixes=(Array.isArray(item.fix)?item.fix:[item.fix]).map(src=>{const el=lineEl(src);el.classList.add('bd-fix');S.lines.appendChild(el);return el;});
    S.fit();
    sayEl.innerHTML=`<div class="bd-k">${ok?'Radai iš pirmo karto ✓':'Klaida buvo '+(item.bad+1)+' žingsnyje'}</div><p><b>Kas negerai.</b> ${say(item.e)}</p>${item.tip?`<p class="bd-mind"><b>🧠 Kaip neapsigauti.</b> ${say(item.tip)}</p>`:''}`;
    if(opt.onResult)opt.onResult(ok);
    for(const el of fixes)await S.write(el,1);
    for(const el of fixes)if(el.dataset.ans){await S.ansLine(el,1);const ov=S.sheet.querySelector('.bd-ov');if(ov.lastChild)ov.lastChild.setAttribute('class','g');}
  }
  function pick(el){
    if(done||!el)return;const j=+el.dataset.step;
    if(j===item.bad){reveal(tries===0);return;}
    tries++;el.classList.add('bd-shake');setTimeout(()=>el.classList.remove('bd-shake'),600);
    const b=S.rel(el.querySelector('.bd-in'));const t=document.createElement('div');t.className='bd-note g';t.textContent='✓ teisinga';t.style.left=(b.x+b.w+44)+'px';t.style.top=(b.y+b.h/2-11)+'px';S.sheet.querySelector('.bd-notes').appendChild(t);
    if(tries>=1)reveal(false);
    else sayEl.innerHTML=`<div class="bd-k">Rask klaidą</div><p>Ši eilutė teisinga. Patikrink kitą – skaičiuok pats, nežiūrėdamas į jau parašytą.</p>`;
  }
  S.lines.addEventListener('click',e=>pick(e.target.closest('.bd-click')));
  S.lines.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();pick(e.target.closest('.bd-click'));}});
  whenFonts().then(draw);
}

window.Board={mount,mistake,md,calcHtml,playCalc,wireCalc};
})();
