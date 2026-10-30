// Start the local app, then run with NODE_PATH pointing to the workspace Playwright package.
// All API responses are mocked; no production session or financial mutations are used.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const out=require('node:path').join(require('node:os').tmpdir(),'royalty-explorer-qa'); fs.mkdirSync(out,{recursive:true});
function dashboard(url) {
 const kw=(url.searchParams.get('keyword')||'').toLowerCase();const own=url.searchParams.get('measure')==='contractual';const track=JSON.parse(url.searchParams.get('drill')||'{}').track_title;
 const amount=(track?(track==='Lost In You'?100:200):300)*(own?.3:1);
 const rank=(name,value=amount)=>({name,amount_usd:value,units:1000,rows:10,percentage:100,identity_key:name.startsWith('Lost In You')?'ISRC:ARDL12600001':null,pending_amount_usd:0});
 return {totals:{amount_usd:amount,units:1000,rows:10,months:1,sources:1,accounts:1,titles:1,artists:1,first_month:'2026-09',last_month:'2026-09'},period_months:['2026-09'],period_basis:'statement_period',keyword:kw,monthly:[{month:'2026-09',amount_usd:amount,units:1000,rows:10}],matrix:[{source:'fuga',account:'indyana',amount_usd:amount,units:1000,rows:10,titles:1,artists:1,months:{'2026-09':amount}}],rankings:{sources:[rank('fuga')],dsp:[rank('YouTube')],monetization:[rank('Content ID')],content_origin:[rank('UGC')],territory:[rank('AR')],sale_type:[],artist:[rank('La Juntada / Candu Domínguez')],title:[...(!track||track==='Lost In You'?[rank('Lost In You',100*(own?.3:1))]:[]),...(!track||track==='Lost In You (Video Oficial)'?[rank('Lost In You (Video Oficial)',200*(own?.3:1))]:[])],label:[rank('Indyana')]},youtube:{totals:{amount_usd:amount,units:1000,titles:1,artists:1},monetization:[rank('Content ID')],content_origin:[rank('UGC')],territory:[rank('AR')],title:[...(!track||track==='Lost In You'?[rank('Lost In You',100*(own?.3:1))]:[]),...(!track||track==='Lost In You (Video Oficial)'?[rank('Lost In You (Video Oficial)',200*(own?.3:1))]:[])]},options:{sources:['fuga'],accounts:['indyana'],source_accounts:[{source:'fuga',account:'indyana'}],first_month:'2026-01',last_month:'2026-09'},catalog_refresh:{status:'ready'},report_personalization:{enabled:false,policy_version:12},...(url.pathname.endsWith('/explore')?{explorer:{measure:own?'contractual':'income',beneficiary:url.searchParams.get('beneficiary'),restricted:false,base_amount_usd:amount/(own?.3:1),pending_amount_usd:0,pending_tracks:0,pending:[],registry_revision:'v1'}}:{})};
}
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try {
 const page=await browser.newPage({viewport:{width:1440,height:1050}});const errors=[],calls=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/api/**',async route=>{
  const u=new URL(route.request().url());calls.push(u.pathname+'?'+u.searchParams);
  let body={};
  if(u.pathname==='/api/session')body={authenticated:true,user:{username:'ui-test',role:'admin',canEdit:true}};
  else if(u.pathname==='/api/royalties-dashboard/explorer-options'){const kw=(u.searchParams.get('keyword')||'').toLowerCase();body={participant:kw==='candu dominguez'?'Candu Domínguez':null,restricted:false};}
  else if(u.pathname==='/api/royalties-dashboard/track') {
   const title=u.searchParams.get('track_title'), amount=title?(title==='Lost In You'?100:200):300;
   body={restricted:false,beneficiary:u.searchParams.get('beneficiary'),registry_revision:'v1',period_basis:'statement_period',tracks:[{
    identity_key:'ISRC:ARDL12600001',isrc:'ARDL12600001',title:title||'Lost In You',row_title:title,base_amount_usd:amount,units:amount*10,pending:[],records:[],segments:[{
     from:'2026-01-01',until:null,version:1,label:'Contrato principal',months:['2026-09'],base_amount_usd:amount,shares:[
      {name:'Candu Domínguez',percent:30,amount_usd:amount*.3,origins:[{label:'Participación directa',percent:30}]},
      {name:'Indyana',percent:70,amount_usd:amount*.7,origins:[{label:'Titular del master',percent:70}]}]}]}]};
  }
  else if(u.pathname.includes('/royalties-dashboard'))body=dashboard(u);
  await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)});
 });
 const origin=process.env.VPO_QA_UI_URL || 'http://127.0.0.1:3142'; assert.ok(['localhost','127.0.0.1'].includes(new URL(origin).hostname),'This mocked UI test runs only against a local app.'); await page.goto(origin);
 await page.getByRole('button',{name:/Dashboard Regalías/}).first().click();
 await page.getByRole('heading',{name:'Dashboard de regalías'}).waitFor();
 const search=page.locator('#royalties_dashboard_keyword');
 await search.fill('lost in you');await search.press('Enter');
 await page.getByRole('button',{name:'Lost In You',exact:true}).first().waitFor();
 assert.equal(await page.locator('select[aria-label="Beneficiario del reparto"]').count(),0);
 assert.equal(await page.getByRole('button',{name:/Ver parte de/}).count(),0);
 await page.screenshot({path:out+'/ui_lost_search.png',fullPage:true});
 await page.getByRole('button',{name:'Lost In You',exact:true}).first().click();
 const dialog=page.getByRole('dialog');await dialog.getByRole('button',{name:'Candu Domínguez',exact:true}).waitFor(); assert.ok((await dialog.getByRole('button',{name:'Cerrar detalle'}).boundingBox()).width<50,'Close action must not inherit the full-width global button style');
 const detailURL=new URL('http://local'+calls.filter(x=>x.startsWith('/api/royalties-dashboard/track?')).at(-1));
 assert.equal(detailURL.searchParams.get('track_key'),'ISRC:ARDL12600001');assert.equal(detailURL.searchParams.get('track_title'),'Lost In You');
 await dialog.getByText(/100,00/).first().waitFor();
 await page.screenshot({path:out+'/ui_lost_split.png',fullPage:true});
 await dialog.getByRole('button',{name:'Cerrar detalle'}).click();
 await page.getByRole('button',{name:'Lost In You (Video Oficial)',exact:true}).first().click();await dialog.getByText(/200,00/).first().waitFor();
 assert.equal(new URL('http://local'+calls.filter(x=>x.startsWith('/api/royalties-dashboard/track?')).at(-1)).searchParams.get('track_title'),'Lost In You (Video Oficial)');
 await dialog.getByRole('button',{name:'Cerrar detalle'}).click();await page.getByRole('button',{name:'Lost In You',exact:true}).first().click();await dialog.getByRole('button',{name:'Candu Domínguez',exact:true}).waitFor();
 await dialog.getByRole('button',{name:'Candu Domínguez',exact:true}).click();
 await page.getByText('Mostrando la parte de Candu Domínguez · Lost In You',{exact:true}).waitFor();
 const topicRequest=calls.filter(x=>x.startsWith('/api/royalties-dashboard/explore?')).at(-1);const topicURL=new URL('http://local'+topicRequest);
 assert.equal(topicURL.searchParams.get('keyword'),'lost in you');assert.equal(JSON.parse(topicURL.searchParams.get('drill')).track,'ISRC:ARDL12600001');assert.equal(JSON.parse(topicURL.searchParams.get('drill')).track_title,'Lost In You');
 await page.screenshot({path:out+'/ui_lost_participant.png',fullPage:true});
 await page.getByRole('button',{name:'Tema: Lost In You'}).click();
 const cleared=new URL('http://local'+calls.filter(x=>x.startsWith('/api/royalties-dashboard/explore?')).at(-1));const clearedDrill=JSON.parse(cleared.searchParams.get('drill')||'{}');assert.equal(clearedDrill.track,undefined);assert.equal(clearedDrill.track_title,undefined);
 await search.fill('Candu Dominguez');await search.press('Enter');
 await page.getByRole('button',{name:'Ver parte de Candu Domínguez',exact:true}).waitFor(); assert.ok((await page.getByRole('button',{name:'Ver parte de Candu Domínguez',exact:true}).boundingBox()).width<300,'Context action must remain an inline link');
 assert.equal(await page.getByText('Mostrando la parte de Candu Domínguez · Lost In You',{exact:true}).count(),0);
 await page.screenshot({path:out+'/ui_candu_search.png',fullPage:true});
 await page.getByRole('button',{name:'Ver parte de Candu Domínguez',exact:true}).click();
 await page.getByRole('button',{name:'Ver ingresos completos',exact:true}).waitFor();
 const ownURL=new URL('http://local'+calls.filter(x=>x.startsWith('/api/royalties-dashboard/explore?')).at(-1));assert.equal(ownURL.searchParams.get('keyword'),'Candu Dominguez');assert.equal(ownURL.searchParams.get('drill'),null);
 await page.screenshot({path:out+'/ui_candu_share.png',fullPage:true});
 await page.getByRole('button',{name:'Ver ingresos completos',exact:true}).click();await page.getByRole('button',{name:'Ver parte de Candu Domínguez',exact:true}).waitFor();
 await search.fill('lost in you');const refreshed=page.waitForResponse(r=>r.url().includes('/api/royalties-dashboard/explorer-options?keyword=lost'));await search.press('Enter');await refreshed;
 assert.equal(await page.getByRole('button',{name:/Ver parte de/}).count(),0);
 await page.setViewportSize({width:390,height:844});await page.getByRole('button',{name:'Lost In You',exact:true}).first().click();await page.getByRole('dialog').getByRole('button',{name:'Cerrar detalle'}).waitFor();assert.ok((await page.getByRole('dialog').boundingBox()).width<=390);await page.screenshot({path:out+'/ui_mobile_split.png'});
 assert.deepEqual(errors,[]);
 fs.writeFileSync(out+'/ui_verified.json',JSON.stringify({calls,errors},null,2));console.log('UI VERIFIED: no selector, title split, participant focus, same search, artist toggle, reset on new search.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
