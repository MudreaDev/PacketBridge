'use strict';
const $ = id => document.getElementById(id);
let ws, connected = false, selected = null, shown = null, metadata = null, lastMove = 0, renderSerial = 0;
const canvas = $('screen'), ctx = canvas.getContext('2d');
function send(data) { if(ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify(data)); }
function command(data) { if(connected && shown && shown === selected) send({...data,window:shown}); }
function status(s) {$('status').textContent = s;}
function clearFrame(){shown=null; metadata=null; renderSerial++;ctx.clearRect(0,0,canvas.width,canvas.height);canvas.classList.remove('ready');$('empty').hidden=false;}
function reset(){connected=false;selected=null;clearFrame();$('connect').disabled=false;$('session').hidden=true;$('join').hidden=false;status('Sesiune închisă');}
$('form').addEventListener('submit', e => {
  e.preventDefault();$('error').textContent='';$('connect').disabled=true;
  const code=$('code').value.replace(/[ -]/g,'').toUpperCase();
  if(!/^[A-Z2-9]{10}$/.test(code)){$('error').textContent='Codul trebuie să conțină 10 caractere.';$('connect').disabled=false;return;}
  ws=new WebSocket(`${location.protocol==='https:'?'wss:':'ws:'}//${location.host}/ws`);
  ws.binaryType='blob';
  ws.onopen=()=>{status('Se verifică sesiunea…');send({type:'join',code});};
  ws.onerror=()=>{$('error').textContent='Conexiune indisponibilă. Verifică adresa serverului.';};
  ws.onclose=reset;
  ws.onmessage=async e=>{
    if(e.data instanceof Blob){
      const meta=metadata, serial=renderSerial;metadata=null;
      try{
        if(!meta || meta.window!==selected)return;
        const img=await createImageBitmap(e.data);
        try{
          if(!connected || serial!==renderSerial || meta.window!==selected)return;
          canvas.width=img.width;canvas.height=img.height;ctx.drawImage(img,0,0);shown=meta.window;
          canvas.classList.add('ready');$('empty').hidden=true;
        }finally{img.close();}
      }catch(err){$('error').textContent='Cadrul nu a putut fi afișat.';}
      finally{send({type:'ack'});}
      return;
    }
    let m;try{m=JSON.parse(e.data);}catch{return;}
    if(m.type==='waiting')status('Aștept acceptul gazdei…');
    else if(m.type==='connected'){connected=true;status('Conectat');$('join').hidden=true;$('session').hidden=false;}
    else if(m.type==='error'){$('error').textContent=m.message;clearFrame();send({type:'release'});}
    else if(m.type==='frame')metadata=m;
    else if(m.type==='windows'){
      const list=$('windows');list.replaceChildren();
      for(const w of m.windows){const o=document.createElement('option');o.value=w.id;o.textContent=w.title;list.append(o);}
      if(!m.windows.some(w=>w.id===selected)){selected=m.windows[0]?.id||null;clearFrame();}
      list.value=selected||'';if(selected)send({type:'select',window:selected});
    }
  };
});
$('windows').onchange=()=>{send({type:'release'});selected=$('windows').value;clearFrame();send({type:'select',window:selected});};
$('disconnect').onclick=()=>{send({type:'release'});ws?.close();};
$('release').onclick=()=>send({type:'release'});
$('sendText').onclick=()=>{const text=$('text').value;if(text)command({type:'text',text});};
$('enter').onclick=()=>command({type:'key',key:'Enter'});
function point(e,action){const r=canvas.getBoundingClientRect();return{type:'pointer',action,x:Math.max(0,Math.min(1,(e.clientX-r.left)/r.width)),y:Math.max(0,Math.min(1,(e.clientY-r.top)/r.height)),button:e.button===2?2:0};}
canvas.onpointerdown=e=>{if(e.button!==0&&e.button!==2)return;e.preventDefault();canvas.focus();canvas.setPointerCapture(e.pointerId);command(point(e,'down'));};
canvas.onpointerup=e=>{command(point(e,'up'));if(canvas.hasPointerCapture(e.pointerId))canvas.releasePointerCapture(e.pointerId);};
canvas.onpointermove=e=>{if(performance.now()-lastMove<25)return;lastMove=performance.now();command(point(e,'move'));};
canvas.onpointercancel=()=>send({type:'release'});
canvas.onlostpointercapture=()=>send({type:'release'});
canvas.ondblclick=e=>{command(point(e,'double'));command(point(e,'up'));};
canvas.oncontextmenu=e=>e.preventDefault();
canvas.addEventListener('wheel',e=>{e.preventDefault();command({...point(e,'wheel'),delta:e.deltaY>0?-120:120});},{passive:false});
const keys=new Set(['Enter','Backspace','Tab','Escape','Delete','ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End','PageUp','PageDown']);
canvas.onkeydown=e=>{if(e.ctrlKey||e.metaKey||e.altKey)return;if(keys.has(e.key)){e.preventDefault();command({type:'key',key:e.key});}else if(e.key.length===1){e.preventDefault();command({type:'text',text:e.key});}};
window.onblur=()=>send({type:'release'});
document.addEventListener('visibilitychange',()=>{if(document.hidden)send({type:'release'});});
