'use strict';
// Keep ISO values in the native control; present a single, editable Russian date.
const DateFields=(()=>{
 const fields=new WeakMap();
 const display=iso=>/^\d{4}-\d{2}-\d{2}$/.test(iso)?iso.split('-').reverse().join('.'):'';
 function parse(value){
  let digits=value.replace(/\D/g,'');
  if(/^\d{4}-\d{2}-\d{2}$/.test(value))digits=value.split('-').reverse().join('');
  if(digits.length!==8)return '';
  const day=Number(digits.slice(0,2)),month=Number(digits.slice(2,4)),year=Number(digits.slice(4)),d=new Date(0);
  d.setUTCFullYear(year,month-1,day);
  return year>=1000&&d.getUTCFullYear()===year&&d.getUTCMonth()===month-1&&d.getUTCDate()===day?digits.slice(4)+'-'+digits.slice(2,4)+'-'+digits.slice(0,2):'';
 }
 function syncAll(except){document.querySelectorAll('input[type=date]').forEach(input=>{const field=fields.get(input);if(field&&field.text!==except&&input.value!==field.lastValue){field.text.value=display(input.value);field.text.setCustomValidity('');field.lastValue=input.value;}});}
 function enhance(input){
  if(fields.has(input)||!input.parentElement)return;
  const wasFocused=document.activeElement===input;
  const label=input.getAttribute('aria-label')||[...(input.closest('label')?.childNodes||[])].filter(n=>n.nodeType===3).map(n=>n.textContent).join('').trim()||'Дата';
  const wrap=document.createElement('span'),text=document.createElement('input'),button=document.createElement('button');
  wrap.className='date-field';text.type='text';text.className=input.className+' date-text';text.id=input.id?input.id+'-text':'';text.inputMode='numeric';text.autocomplete='off';text.placeholder='ДД.ММ.ГГГГ';text.maxLength=10;text.required=input.required;text.value=display(input.value);text.setAttribute('aria-label',label);
  button.type='button';button.className='date-calendar';button.setAttribute('aria-label','Открыть календарь: '+label.toLowerCase());button.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="4" y="5" width="16" height="16" rx="3"/><path d="M8 3v4m8-4v4M4 11h16"/></svg>';
  input.before(wrap);wrap.append(text,button,input);input.classList.add('date-native');input.tabIndex=-1;input.setAttribute('aria-hidden','true');fields.set(input,{text,lastValue:input.value});
  input.addEventListener('focus',()=>text.focus({preventScroll:true}));
  input.addEventListener('input',()=>queueMicrotask(()=>syncAll(document.activeElement===text?text:null)));
  input.addEventListener('change',()=>{text.value=display(input.value);text.setCustomValidity('');queueMicrotask(()=>syncAll());});
  input.addEventListener('invalid',e=>{e.preventDefault();text.setCustomValidity(input.validationMessage);text.reportValidity();});
  let selectOnRelease=false;
  text.addEventListener('pointerdown',()=>selectOnRelease=document.activeElement!==text);
  text.addEventListener('pointerup',()=>{if(selectOnRelease){text.select();selectOnRelease=false;}});
  text.addEventListener('focus',()=>text.select());
  text.addEventListener('keydown',e=>{if(text.selectionStart!==text.selectionEnd)return;const pos=text.selectionStart;if(e.key==='Backspace'&&text.value[pos-1]==='.')text.setSelectionRange(pos-1,pos-1);if(e.key==='Delete'&&text.value[pos]==='.')text.setSelectionRange(pos+1,pos+1);});
  text.addEventListener('input',()=>{
   const raw=text.value,iso=parse(raw),digits=/^\d{4}-\d{2}-\d{2}$/.test(raw)?raw.split('-').reverse().join(''):raw.replace(/\D/g,'').slice(0,8),before=raw.slice(0,text.selectionStart).replace(/\D/g,'').length;
   const formatted=digits.slice(0,2)+(digits.length>2?'.'+digits.slice(2,4):'')+(digits.length>4?'.'+digits.slice(4):'');
   text.value=formatted;let caret=0,count=0;while(caret<formatted.length&&count<before){if(/\d/.test(formatted[caret]))count++;caret++;}text.setSelectionRange(caret,caret);
   input.value=iso;fields.get(input).lastValue=iso;input.dispatchEvent(new Event('input',{bubbles:true}));
   // Changes such as checkout's minimum date still run through existing handlers.
   if(iso||!digits)input.dispatchEvent(new Event('change',{bubbles:true}));
   text.value=formatted;text.setCustomValidity(digits&&!iso?'Введите существующую дату в формате ДД.ММ.ГГГГ':input.validationMessage);
   syncAll(text);
  });
  text.addEventListener('blur',()=>{if(parse(text.value))text.value=display(input.value);});
  button.onclick=()=>{text.setCustomValidity('');if(typeof input.showPicker==='function')input.showPicker();else input.click();};
  if(wasFocused)text.focus({preventScroll:true});
 }
 function scan(){document.querySelectorAll('input[type=date]').forEach(enhance);}
 new MutationObserver(scan).observe(document.documentElement,{childList:true,subtree:true});scan();
 return {parse,sync:syncAll};
})();
