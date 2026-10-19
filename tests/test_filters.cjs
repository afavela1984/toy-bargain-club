// Execute the actual embedded shopping script against a small DOM test double.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('templates/site.html','utf8').match(/<script>([\s\S]*?)<\/script>/)[1];
function control(value=''){return {value,events:{},textContent:'',hidden:false,children:[],addEventListener(n,f){this.events[n]=f},setAttribute(n,v){this[n]=v},append(c){this.children=this.children.filter(x=>x!==c);this.children.push(c)}}}
const ids={};for(const id of ['category','minimum','sort','age-filter','price-filter','search','count','fav-count','favorites','reset','grid','no-results'])ids[id]=control();
Object.assign(ids.category,{value:'All'});ids.minimum.value='25';ids.sort.value='discount';ids['age-filter'].value='all';ids['price-filter'].value='all';
function card(id,price,age,discount){const fav=control(),verified=control();return {dataset:{id,price:String(price),age:String(age),discount:String(discount),savings:String(price),category:'Toys',name:id,checked:new Date().toISOString(),expires:new Date(Date.now()+3600000).toISOString()},hidden:false,querySelector:s=>s==='.favorite'?fav:verified,remove(){this.removed=true}}}
const cards=[card('lego',20,6,50),card('barbie',35,3,40),card('puzzle',10,12,25)];
let stored='[]';vm.runInNewContext(source,{document:{getElementById:id=>ids[id],querySelectorAll:()=>cards,createElement:()=>control()},localStorage:{getItem:()=>stored,setItem:(k,v)=>stored=v},setTimeout(){},location:{reload(){}},Date,Set,Number,Math,JSON});
assert.equal(ids.count.textContent,'3 of 3 finds');
ids.search.value='lego';ids.search.events.input();assert.equal(ids.count.textContent,'1 of 3 finds');
ids.reset.events.click();ids['age-filter'].value='3-5';ids['age-filter'].events.change();assert.equal(ids.count.textContent,'1 of 3 finds');assert.equal(cards[1].hidden,false);
ids.reset.events.click();ids['price-filter'].value='0-15';ids['price-filter'].events.change();assert.equal(ids.count.textContent,'1 of 3 finds');assert.equal(cards[2].hidden,false);
ids.reset.events.click();ids.minimum.value='50';ids.minimum.events.change();assert.equal(ids.count.textContent,'1 of 3 finds');
ids.reset.events.click();ids.sort.value='price-low';ids.sort.events.change();assert.equal(ids.grid.children[0].dataset.id,'puzzle');
ids.grid.events.click({target:{closest:()=>({dataset:{fav:'lego'}})}});assert.equal(stored,'["lego"]');ids.favorites.events.click();assert.equal(ids.count.textContent,'1 of 3 finds');
ids.search.value='nothing';ids.search.events.input();assert.equal(ids['no-results'].hidden,false);
console.log('Shopping script passed: search, age, price, discount, sorting, favorites, reset and empty results.');
