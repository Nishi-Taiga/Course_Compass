#!/usr/bin/env node
const fs = require('fs');
const path = require('path');

const BASE = path.resolve(__dirname, '..');
const SEED = path.join(BASE, 'data', 'seed');
const PROTO = path.join(BASE, 'prototype', 'index.html');

const MEET_RANK = {"全国大会（インターハイ）":3,"全国大会（定時制通信制）":3,"全国大会":3,"関東大会":2,"東京都大会":1,"東京都大会（予選）":1};

function rankScore(rank){
  if(rank==='優勝') return 100;
  if(rank==='準優勝') return 95;
  let m=rank.match(/ベスト\s*(\d+)/); if(m) return Math.max(50,90-parseInt(m[1]));
  m=rank.match(/(\d+)\s*位/); if(m) return Math.max(20,92-parseInt(m[1])*2);
  if(rank.startsWith('金賞')) return rank.includes('最優秀')?88:75;
  if(rank.startsWith('銀賞')) return 55;
  if(rank.startsWith('銅賞')) return 40;
  if(rank==='入賞') return 70;
  if(rank==='佳作') return 45;
  m=rank.match(/([一二三四五六七八九])回戦(進出|出場)/);
  if(m) return 12+'一二三四五六七八九'.indexOf(m[1])*6+6;
  if(rank.includes('出場')) return 15;
  m=rank.match(/(\d+)\s*回戦/); if(m) return 10+parseInt(m[1]);
  return 5;
}

function labelSport(row){
  const sport=(row.sport||'').trim();
  const event=(row.event||'').trim();
  if(sport&&event&&event!=='団体'&&!event.includes(sport)){
    return (sport+event).length<=16?sport+event:sport;
  }
  return sport||event;
}

function parseCSV(file){
  if(!fs.existsSync(file)) return [];
  const lines=fs.readFileSync(file,'utf-8').replace(/^\uFEFF/,'').split('\n').filter(l=>l.trim());
  if(!lines.length) return [];
  const headers=lines[0].split(',');
  return lines.slice(1).map(l=>{
    const cols=l.split(',');
    const obj={};
    headers.forEach((h,i)=>obj[h.trim()]=((cols[i]||'').trim()));
    return obj;
  });
}

function loadSiteRows(){
  const rows=parseCSV(path.join(SEED,'school_club_achievements_sites.csv'));
  const re=/優勝|準優勝|ベスト\s*[0-9０-９]+|第?\s*[0-9０-９]+\s*位|入賞|金賞|銀賞|銅賞|出場/;
  return rows.filter(r=>r.flag==='OK'&&r.club&&r.meet).map(r=>{
    const m=(r.text||'').match(re);
    if(!m) return null;
    return {school:r.school,sport:r.club,event:'',division:'',meet:r.meet,rank:m[0],year:r.year,origin:'学校公式サイト'};
  }).filter(Boolean);
}

function loadSuisou(){
  const rows=parseCSV(path.join(SEED,'school_suisou_results.csv'));
  return rows.map(r=>{
    const kumi=(r.event||'').trim();
    return {...r,sport:'吹奏楽',event:'',rank:kumi?`${r.rank}（${kumi}）`:r.rank,meet:'東京都大会',origin:'東京都吹奏楽連盟'};
  });
}

function loadIfac(){
  const rows=parseCSV(path.join(SEED,'school_ifac_results.csv'));
  return rows.map(r=>({...r,meet:'全国大会',origin:'高校生国際美術展'}));
}

function loadBaseball(){
  const rows=parseCSV(path.join(SEED,'school_baseball_results.csv'));
  return rows.map(r=>({...r,meet:'東京都大会',origin:'東京都高等学校野球連盟'}));
}

function displayRank(meet,rank){
  if(rank.includes('賞')||rank==='入賞'||rank==='佳作') return rank;
  if((MEET_RANK[meet]||0)<2) return rank;
  let m=rank.match(/^(?:決勝|準決勝|準々決勝|予選)?\s*(\d+)\s*位$/);
  if(m&&parseInt(m[1])>8) return '出場';
  if(/^\d+\s*回戦$/.test(rank)) return '出場';
  return rank;
}

const main = () => {
  const srcRows = parseCSV(path.join(SEED, 'school_club_achievements.csv')).filter(r=>r.sport||r.event);
  srcRows.forEach(r=>r.origin='都高体連');
  const allRows = [...srcRows, ...loadSuisou(), ...loadIfac(), ...loadBaseball()];

  const best = {};
  const allWithSites = [...allRows, ...loadSiteRows()];
  for(const r of allWithSites){
    const sport = labelSport(r);
    if(!sport) continue;
    const key = `${r.school}|${sport}|${r.division}`;
    const score = (MEET_RANK[r.meet]||0)*1000 + rankScore(r.rank);
    const cur = best[key];
    if(cur && cur.origin==='都高体連' && r.origin!=='都高体連') continue;
    if(!cur || score>cur._score){
      best[key]={_score:score,school:r.school,sport,division:r.division,meet:r.meet,rank:r.rank,year:r.year,origin:r.origin};
    }
  }

  const bySchool = {};
  for(const v of Object.values(best)){
    if(!bySchool[v.school]) bySchool[v.school]=[];
    bySchool[v.school].push(v);
  }

  const out = {};
  for(const [school,items] of Object.entries(bySchool)){
    items.sort((a,b)=>b._score-a._score);
    const specific = new Set(items.map(i=>`${i.sport}|${i.division}`));
    const filtered = items.filter(i=>!items.some(o=>o!==i&&o.sport.startsWith(i.sport)&&i.sport!==o.sport&&o.division===i.division));
    out[school] = filtered.map(i=>({
      sp:i.sport,dv:i.division,mt:i.meet,rk:displayRank(i.meet,i.rank),yr:i.year,sr:i.origin
    }));
    // No MAX_PER_SCHOOL limit — show all achievements
  }

  const html = fs.readFileSync(PROTO, 'utf8');
  const start = html.indexOf('const D = ');
  const nl = html.indexOf('\n', start);
  const jsonEnd = html.charAt(nl-1)==='\r' ? nl-1 : nl;
  const data = JSON.parse(html.slice(start + 'const D = '.length, jsonEnd).replace(/;$/,''));

  let added = 0;
  for(const s of data.schools){
    const ach = out[s.n];
    if(ach && ach.length){
      s.ach = ach;
      added++;
    } else {
      delete s.ach;
    }
  }

  const newHtml = html.slice(0, start) + 'const D = ' + JSON.stringify(data) + ';' + html.slice(nl);
  fs.writeFileSync(PROTO, newHtml, 'utf8');
  console.log(`Done: ${added} schools with achievements (no limit)`);
};

main();
