// Export the real UI to PDF using a saved-booking fixture; no model/server needed.
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const {chromium} = require(path.join(root, '.runtime/browser/node_modules/playwright-core'));
const web = path.join(root, 'backend/core/web');
const output = path.resolve(root, '../output/pdf');
const hotel = {
  image_url:'/assets/stay-a.webp',id:'example-hotel',name:'Загородный отель «Лес и озеро»',address:'Карелия, Сортавала, улица Лесная, 12',
  rating:9.4,stars:4,distance_m:3200,amenities:['Wi-Fi','Парковка','Спа'],
  reasons:['Загородный формат размещения','В вашем бюджете','Высокая оценка гостей'],
  unverified:['Лес у отеля и степень уединения'],url:'https://ostrovok.ru/hotel/russia/sortavala/',
  quote:{source_kind:'demo',currency:'RUB',nightly_minor:690000,total_minor:3450000,nights:5,rooms:1,breakfast:false,free_cancellation:false}
};
const booking = {id:'OP-EXAMPLE',is_demo:true,hotel,quote:hotel.quote,dates:{start:'2026-11-10',end:'2026-11-15'},guest_name:'Александр Иванов',travellers:{adults:2,children:[]},created_at:'2026-10-27T12:00:00Z'};
const snapshot = {session_id:'a'.repeat(32),revision:3,status:'hotel_booked',search_mode:'hotels',hotel_booking:booking,trip_spec:{destination:'Сортавала',travel_setting:'forest',travellers:booking.travellers},assistant_message:'План поездки сохранён.'};
const server=http.createServer((req,res)=>{
  const file=path.resolve(web,'.'+new URL(req.url,'http://localhost').pathname);
  if(!file.startsWith(web+path.sep)){res.writeHead(403).end();return;}
  const types={'.html':'text/html','.js':'application/javascript','.css':'text/css','.svg':'image/svg+xml','.woff2':'font/woff2'};
  fs.readFile(file,(error,data)=>{if(error){res.writeHead(404).end();return;}res.setHeader('Content-Type',types[path.extname(file)]||'application/octet-stream');res.end(data);});
});
(async()=>{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  fs.mkdirSync(output,{recursive:true});
  const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
  try {
    const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
    page.setDefaultTimeout(15000);
    await page.route('**/api/sessions/**',route=>route.fulfill({json:snapshot}));
    await page.goto(`http://127.0.0.1:${server.address().port}/plan.html`);
    const button=page.getByRole('button',{name:'Скачать план поездки · PDF',exact:true});
    await button.waitFor();
    assert.equal(await page.evaluate(()=>!!window.PDFLib),false,'PDF libraries should load only when exporting');
    // A failed font fetch must restore the action and permit a real retry.
    await page.route('**/assets/root-regular.ttf',route=>route.fulfill({status:503,body:''}));
    await button.click();await page.getByRole('alert').filter({hasText:'Не удалось подготовить PDF'}).waitFor();
    await page.waitForFunction(()=>!document.querySelector('[aria-busy="true"]'));
    assert.equal(await button.isEnabled(),true);
    await page.unroute('**/assets/root-regular.ttf');
    await page.evaluate(async b => (await TripPDF.create(b,{destination:'Сортавала',travel_setting:'forest'})).length,booking);
    const downloaded=page.waitForEvent('download');await button.click();const download=await downloaded;
    assert.equal(download.suggestedFilename(),'OPlan-OP-EXAMPLE.pdf');
    await download.saveAs(path.join(output,'oplan-example.pdf'));
    const {PDFDocument}=require(path.join(web,'assets/vendor/pdf-lib-1.17.1.min.js'));
    const pdf=await PDFDocument.load(fs.readFileSync(path.join(output,'oplan-example.pdf')));
    assert.equal(pdf.getPageCount(),1);
    assert.equal(pdf.getPage(0).node.Resources().lookup(require(path.join(web,'assets/vendor/pdf-lib-1.17.1.min.js')).PDFName.of('XObject')).keys().length, 2, 'Logo and hotel photo must be embedded');
    assert.equal(pdf.getTitle(),'План поездки · Сортавала');
    await page.waitForFunction(()=>!document.querySelector('[aria-busy="true"]'));
    assert.equal(await button.isEnabled(),true);
    const fallback = await page.evaluate(async b => {
      b.hotel.image_url='/assets/missing-photo.jpg'; b.hotel.images=[];
      return Array.from(await TripPDF.create(b,{destination:'Сочи'}));
    }, booking);
    fs.writeFileSync(path.join(output,'oplan-destination-example.pdf'),Buffer.from(fallback));
    const fallbackPdf=await PDFDocument.load(Uint8Array.from(fallback));
    assert.equal(fallbackPdf.getPage(0).node.Resources().lookup(require(path.join(web,'assets/vendor/pdf-lib-1.17.1.min.js')).PDFName.of('XObject')).keys().length,2);
    const more=structuredClone(booking);more.id='OP-LONG';more.guest_name='Анна-Мария Александрова-Смирнова';more.travellers.children=[5,9];more.quote={...more.quote,breakfast:true,free_cancellation:true};
    more.hotel={...more.hotel,name:'Загородный комплекс «Очень длинное название отеля для проверки переноса строк в документе»',reasons:Array.from({length:9},(_,i)=>'Пожелание '+(i+1)+': '+('подробное описание выбранного размещения и условий поездки. '.repeat(4))),amenities:['Wi-Fi','Детская площадка'],url:'javascript:alert(1)'};
    const long=await page.evaluate(async b=>Array.from(await TripPDF.create(b,{destination:'Сортавала',travel_setting:'forest'})),more);
    fs.mkdirSync(path.join(root,'.runtime/screenshots/trip-pdf'),{recursive:true});
    fs.writeFileSync(path.join(root,'.runtime/screenshots/trip-pdf/long.pdf'),Buffer.from(long));
    const longPdf=await PDFDocument.load(Uint8Array.from(long));
    assert.ok(longPdf.getPageCount()>1);
    assert.ok(longPdf.getPages().every(p=>(p.node.Annots()?.size()||0)===0),'Unsafe hotel URLs must not produce links');
    assert.deepEqual(errors,[]);
    console.log('PASS: PDF download, local lazy assets, failed-asset retry, children, both tariff branches, long content, unsafe link');
  } finally {await browser.close();server.close();}
})().catch(error=>{console.error(error);server.close();process.exitCode=1;});
