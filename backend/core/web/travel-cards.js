'use strict';
// Decorative local photos only. Sources and license live beside the WebP files.
const TravelCards = (() => {
  const motion = matchMedia('(prefers-reduced-motion: reduce)');
  const photos = Array.from({length:24}, (_,i) => '/assets/travel-cards/'+String(i+1).padStart(2,'0')+'.webp');
  let ready = [], preload;
  function warm() {
    if (motion.matches) return Promise.resolve([]);
    if (!preload) preload = Promise.all(photos.map(async src => {
      const image = new Image(); image.decoding = 'async'; image.src = src;
      try { await image.decode(); ready.push(image); } catch { /* Skip missing photos. */ }
    }));
    return preload;
  }
  // Decode on page entry, before a request. Flights only use decoded images.
  warm();
  function shuffled(items) {
    const bag = [...items];
    for (let i=bag.length-1;i>0;i--) { const j=Math.floor(Math.random()*(i+1)); [bag[i],bag[j]]=[bag[j],bag[i]]; }
    return bag;
  }
  function mount(mark) {
    const layer = document.createElement('div');
    layer.className = 'ow-photo-layer'; layer.setAttribute('aria-hidden','true');
    mark.prepend(layer);
    // Subtract the entire rounded outer silhouette, INCLUDING the O's opening.
    // Coordinates match the unchanged 245 × 300 ring at (8, 0) in the mark.
    const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="860" height="430" viewBox="0 0 860 430"><defs><mask id="cut"><rect width="860" height="430" fill="white"/><rect x="288" y="65" width="245" height="300" rx="117.6" ry="144" fill="black"/></mask></defs><rect width="860" height="430" fill="white" mask="url(#cut)"/></svg>';
    const mask = 'url("data:image/svg+xml,'+encodeURIComponent(svg)+'")';
    layer.style.maskImage = mask; layer.style.webkitMaskImage = mask;
    let timer, stopped = false, generation = 0, photoBag = [], routeBag = [], lastPhoto, lastRoute, drain;
    const flights = new Set();
    // Opposing directions, with an independent shuffle and mild variation per flight.
    // Diagonals leave more viewing room than a short vertical path above/below O.
    const routes = [[-1,-.3],[1,.3],[-.85,.6],[.85,-.6],[-.65,-.8],[.65,.8],[-1,.15],[1,-.15]];
    function nextPhoto() {
      if (!photoBag.length) {
        photoBag = shuffled(ready);
        if (photoBag.length>1 && photoBag.at(-1)===lastPhoto) [photoBag[0],photoBag[photoBag.length-1]]=[photoBag.at(-1),photoBag[0]];
      }
      return lastPhoto = photoBag.pop();
    }
    function launch() {
      if (stopped || motion.matches || document.hidden) return;
      if (ready.length && flights.size<3 && mark.isConnected) {
        if (!routeBag.length) {
          routeBag = shuffled(routes);
          if (routeBag.at(-1)===lastRoute) [routeBag[0],routeBag[routeBag.length-1]]=[routeBag.at(-1),routeBag[0]];
        }
        const [dx,dy] = lastRoute = routeBag.pop();
        const mobile = matchMedia('(max-width: 760px)').matches;
        const compact = !!mark.closest('.compact');
        const rangeX = compact ? 210 : mobile ? 212 : 340;
        const rangeY = compact ? 152 : mobile ? 168 : 188;
        const x=dx*rangeX, y=dy*rangeY, angle=(Math.random()-.5)*22;
        const card=nextPhoto().cloneNode();
        card.className='ow-photo-card'; card.alt=''; card.draggable=false;
        layer.append(card);
        const transform=(x,y,r,s)=>`translate(-50%, -50%) translate(${x}px, ${y}px) rotate(${r}deg) scale(${s})`;
        const flight=card.animate([
          {offset:0,opacity:0,transform:transform(x,y,angle,.96)},
          {offset:.12,opacity:1,transform:transform(x*.94,y*.94,angle*.9,1)},
          {offset:.55,opacity:1,transform:transform(x*.56,y*.56,angle*.4,1)},
          {offset:1,opacity:1,transform:transform(0,0,-angle*.25,.68)}
        ],{duration:3300+Math.random()*200,easing:'cubic-bezier(.35,0,.65,1)',fill:'forwards'});
        flights.add(flight);
        flight.finished.then(()=>{flights.delete(flight);card.remove();},()=>{flights.delete(flight);card.remove();});
      }
      // Three intervals exceed the longest flight, preserving the three-card cap.
      timer=setTimeout(launch,1180+Math.random()*20);
    }
    function clearFlights() {
      clearTimeout(timer);
      flights.forEach(flight=>flight.cancel()); flights.clear();
      layer.replaceChildren();
    }
    function resume() {
      const version=++generation;clearFlights();
      if (!stopped && !motion.matches && !document.hidden) {
        warm().then(()=>{if(version===generation&&!stopped)launch();});
      }
    }
    motion.addEventListener('change',resume);
    document.addEventListener('visibilitychange',resume);
    resume();
    return {
      stop(immediate=false) {
        if (stopped) return drain || Promise.resolve();
        stopped=true; clearTimeout(timer);
        motion.removeEventListener('change',resume);
        document.removeEventListener('visibilitychange',resume);
        if (immediate || motion.matches || document.hidden || !flights.size) {
          clearFlights(); layer.remove(); return Promise.resolve();
        }
        // Keep existing trajectories, stop births immediately, fade within 250 ms.
        const fade=layer.animate([{opacity:1},{opacity:0}],{duration:250,easing:'ease-out',fill:'forwards'});
        // A hidden panel or suspended compositor must not retain the waiting shell.
        let deadline;
        drain=Promise.race([fade.finished.catch(()=>{}),new Promise(resolve=>{deadline=setTimeout(resolve,250);})])
          .then(()=>{clearTimeout(deadline);clearFlights();fade.cancel();layer.remove();});
        return drain;
      }
    };
  }
  return {mount};
})();
