from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .config import load_config, select_classes
from .workflow import qa_valid


STYLE = """
:root{--ink:#183126;--muted:#617168;--line:#d8e3dc;--paper:#fff;--wash:#f3f7f4;--accent:#176b45;--warn:#9a5c00}
*{box-sizing:border-box}html,body{margin:0;min-height:100%;background:var(--wash);color:var(--ink);font-family:Arial,sans-serif}body{padding-bottom:135px}
header{background:#143e2c;color:#fff;padding:9px 18px;display:flex;gap:18px;align-items:baseline}header h1{margin:0;font-size:19px}header p{margin:0;color:#d8e9df;font-size:13px}
main{max-width:1800px;margin:8px auto;padding:0 10px}.card{background:var(--paper);border:1px solid var(--line);border-radius:7px;padding:7px}.card h3{margin:0 0 3px;font-size:13px}
.timeline-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px;margin-bottom:7px}.timeline svg{height:105px}.visual-layout{display:grid;grid-template-columns:minmax(560px,1.15fr) minmax(620px,1fr);gap:7px}.combined svg{height:clamp(320px,44vh,470px)}
.candidate-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}.candidate-grid svg{height:clamp(150px,20.5vh,225px)}svg{width:100%;display:block}.status{color:var(--muted);font-size:12px}.warning{color:var(--warn);font-weight:700;font-size:12px}.active-mode{background:var(--accent)!important;color:#fff!important;border-color:var(--accent)!important}
.control-dock{position:fixed;left:0;right:0;bottom:0;z-index:10;background:#fff;border-top:2px solid var(--accent);box-shadow:0 -4px 16px #143e2c22;padding:8px 12px}.dock-inner{max-width:1800px;margin:auto;display:grid;grid-template-columns:minmax(520px,1.25fr) minmax(620px,1fr);gap:10px;align-items:center}.review-row,.nav-row{display:flex;gap:7px;align-items:center;flex-wrap:wrap}.review-title{font-weight:700;font-size:13px}.checks{display:flex;gap:5px;flex-wrap:wrap}.check{display:inline-flex;gap:4px;align-items:center;padding:6px 8px;border:1px solid var(--line);border-radius:5px;background:#fafcfb;font-weight:700}.check input{accent-color:var(--accent)}
.control-dock button,.control-dock select{padding:7px 9px;border:1px solid #9bb1a3;border-radius:5px;background:#fff;cursor:pointer}.saved{color:var(--accent);font-size:12px}.shortcuts{font-size:11px;color:var(--muted);width:100%}
@media(max-width:1100px){body{padding-bottom:210px}.visual-layout{grid-template-columns:1fr}.combined svg{height:330px}.candidate-grid svg{height:190px}.dock-inner{grid-template-columns:1fr}}
@media(max-width:700px){body{padding-bottom:0}.timeline-grid,.candidate-grid{grid-template-columns:1fr}.control-dock{position:static}.visual-layout{display:block}.dock-inner{display:block}}
"""


def _indices(records: list[dict[str, Any]]) -> dict[str, float | None]:
    values: dict[str, list[float]] = {"evi": [], "bsi": []}
    for record in records:
        blue, red, nir, swir = (float(record[name]) for name in ["B02", "B04", "B08", "B11"])
        evi_den = nir + 6 * red - 7.5 * blue + 1
        bsi_den = swir + red + nir + blue
        if np.isfinite(evi_den) and abs(evi_den) > 1e-12:
            values["evi"].append(2.5 * (nir - red) / evi_den)
        if np.isfinite(bsi_den) and abs(bsi_den) > 1e-12:
            values["bsi"].append(((swir + red) - (nir + blue)) / bsi_den)
    result: dict[str, float | None] = {}
    for name, data in values.items():
        result[f"{name}_median"] = float(np.median(data)) if data else None
        result[f"{name}_std"] = float(np.std(data, ddof=0)) if data else None
    return result


def _script(code: str, class_name: str, payload: list[dict[str, Any]], bands: list[str], reflectance_max: float) -> str:
    return f"""
const CLASS_CODE={json.dumps(code)},CLASS_NAME={json.dumps(class_name)},DATES={json.dumps(payload, ensure_ascii=False, separators=(',', ':'))},BANDS={json.dumps(bands)},MAX={reflectance_max!r};
let current=0,mode='raw';const COLORS=['#176b45','#d97706','#2563a8','#8b3a8c'],storageKey='wtss1000-review-'+CLASS_CODE;
const saved=()=>{{try{{return JSON.parse(localStorage.getItem(storageKey)||'{{}}')}}catch(e){{return {{}}}}}};
function values(v){{if(mode==='raw')return v;const lo=Math.min(...v),hi=Math.max(...v),span=Math.max(hi-lo,1e-9);return v.map(x=>(x-lo)/span)}}
function plot(id,series,context=[],mean=null){{const svg=document.getElementById(id),W=700,H=id==='combined'?500:255,p=38;svg.innerHTML='';if(!series.length)return;const hi=mode==='raw'?MAX:1,point=v=>v.map((x,i)=>`${{p+i*(W-2*p)/(BANDS.length-1)}},${{H-p-values(v)[i]/hi*(H-2*p)}}`).join(' '),el=(n,a)=>{{const z=document.createElementNS('http://www.w3.org/2000/svg',n);Object.entries(a).forEach(([k,v])=>z.setAttribute(k,v));svg.appendChild(z);return z}};el('line',{{x1:p,y1:H-p,x2:W-p,y2:H-p,stroke:'#9bb1a3'}});el('line',{{x1:p,y1:p,x2:p,y2:H-p,stroke:'#9bb1a3'}});BANDS.forEach((b,i)=>{{const t=el('text',{{x:p+i*(W-2*p)/(BANDS.length-1),y:H-10,'text-anchor':'middle','font-size':11,fill:'#617168'}});t.textContent=b}});context.forEach(v=>el('polyline',{{points:point(v),fill:'none',stroke:'#a9afac','stroke-width':0.8,opacity:0.5}}));if(mean)el('polyline',{{points:point(mean),fill:'none',stroke:'#303733','stroke-width':1.6,'stroke-dasharray':'5 4'}});series.forEach((s,i)=>{{el('polyline',{{points:point(s.values),fill:'none',stroke:s.color,'stroke-width':3}});const t=el('text',{{x:W-p,y:p+14*i,'text-anchor':'end','font-size':12,fill:s.color}});t.textContent=s.label}})}}
function temporal(id,key,color,bars=false){{const svg=document.getElementById(id),W=750,H=105,p={{l:42,r:18,t:15,b:24}},valid=DATES.filter(d=>Number.isFinite(d[key])),vals=valid.map(d=>d[key]),lo=bars?0:Math.min(...vals),hi=Math.max(...vals)||1,t0=Date.parse(DATES[0].date),t1=Date.parse(DATES.at(-1).date),x=d=>p.l+(Date.parse(d.date)-t0)/(t1-t0)*(W-p.l-p.r),y=v=>H-p.b-(v-lo)/Math.max(hi-lo,1e-9)*(H-p.t-p.b),el=(n,a)=>{{const z=document.createElementNS('http://www.w3.org/2000/svg',n);Object.entries(a).forEach(([k,v])=>z.setAttribute(k,v));svg.appendChild(z);return z}};svg.innerHTML='';el('line',{{x1:p.l,y1:H-p.b,x2:W-p.r,y2:H-p.b,stroke:'#9bb1a3'}});if(bars)valid.forEach(d=>el('rect',{{x:x(d)-1,y:y(d[key]),width:2,height:H-p.b-y(d[key]),fill:color,opacity:.75}}));else el('polyline',{{points:valid.map(d=>`${{x(d)}},${{y(d[key])}}`).join(' '),fill:'none',stroke:color,'stroke-width':2}});const mx=x(DATES[current]);el('line',{{x1:mx,y1:p.t,x2:mx,y2:H-p.b,stroke:'#c2410c','stroke-width':2}})}}
function persist(labels){{const d=DATES[current],all=saved();if(labels===null)all[d.date]={{active_vegetation_endmembers:'NENHUM',candidate_ids:'',reviewed_at:new Date().toISOString()}};else if(labels.length){{const c=d.candidates.filter(x=>labels.includes(x.label));all[d.date]={{active_vegetation_endmembers:c.map(x=>x.label).join('|'),candidate_ids:c.map(x=>x.candidate_id).join('|'),reviewed_at:new Date().toISOString()}}}}else delete all[d.date];localStorage.setItem(storageKey,JSON.stringify(all));render()}}
function render(){{const d=DATES[current],all=saved(),rec=all[d.date],selected=(rec?.active_vegetation_endmembers||'').split('|').filter(x=>x&&x!=='NENHUM'),series=d.candidates.map((c,i)=>({{label:c.label,values:BANDS.map(b=>Number(c[b])),color:COLORS[i]}}));document.getElementById('date').textContent=d.date;document.getElementById('counter').textContent=`${{current+1}} / ${{DATES.length}} — revisadas: ${{Object.keys(all).length}}`;document.getElementById('jump').value=current;document.getElementById('qa').textContent=`Pixels válidos: ${{d.valid_pixels}} / 1.000${{d.warning?' — '+d.warning:''}}`;plot('combined',series);for(let i=0;i<4;i++){{document.getElementById('title'+i).textContent=series[i]?series[i].label:'EM0'+(i+1)+' — indisponível';plot('plot'+i,series[i]?[series[i]]:[],d.context,d.mean)}}temporal('evi','evi_median','#176b45');temporal('bsi','bsi_median','#9a5c00');temporal('evi-std','evi_std','#71a987',true);temporal('bsi-std','bsi_std','#d6a24d',true);const options=document.getElementById('options');options.innerHTML='';d.candidates.forEach(c=>{{const label=document.createElement('label'),input=document.createElement('input');label.className='check';input.type='checkbox';input.checked=selected.includes(c.label);input.onchange=()=>persist(Array.from(options.querySelectorAll('input:checked')).map(x=>x.value));input.value=c.label;label.append(input,c.label);options.append(label)}});document.getElementById('saved').textContent=rec?.active_vegetation_endmembers||'Pendente';document.getElementById('raw').className=mode==='raw'?'active-mode':'';document.getElementById('shape').className=mode==='shape'?'active-mode':''}}
document.getElementById('prev').onclick=()=>{{current=(current-1+DATES.length)%DATES.length;render()}};document.getElementById('next').onclick=()=>{{current=(current+1)%DATES.length;render()}};document.getElementById('jump').onchange=e=>{{current=Number(e.target.value);render()}};document.getElementById('all').onclick=()=>persist(DATES[current].candidates.map(c=>c.label));document.getElementById('none').onclick=()=>persist(null);document.getElementById('raw').onclick=()=>{{mode='raw';render()}};document.getElementById('shape').onclick=()=>{{mode='shape';render()}};
document.getElementById('export').onclick=()=>{{const all=saved(),rows=['class_code,date,active_vegetation_endmembers,candidate_ids,reviewed_at'];DATES.forEach(d=>{{if(all[d.date]){{const r=all[d.date];rows.push([CLASS_CODE,d.date,r.active_vegetation_endmembers,r.candidate_ids,r.reviewed_at].map(v=>'"'+String(v||'').replaceAll('"','""')+'"').join(','))}}}});const blob=new Blob([rows.join('\\n')],{{type:'text/csv;charset=utf-8'}}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=`wtss1000_active_vegetation_class_${{CLASS_CODE}}.csv`;a.click();URL.revokeObjectURL(a.href)}};
DATES.forEach((d,i)=>{{const o=document.createElement('option');o.value=i;o.textContent=d.date;document.getElementById('jump').appendChild(o)}});render();
"""


def _page(code: str, class_name: str, payload: list[dict[str, Any]], bands: list[str], maximum: float) -> str:
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Classe {code}</title><style>{STYLE}</style></head><body>
<header><h1>Classe {code} — {html.escape(class_name)}</h1><p>Identificação de candidatos com assinatura de vegetação fotossinteticamente ativa</p></header><main>
<section class="timeline-grid"><article class="card timeline"><h3>EVI mediano dos candidatos PPI</h3><svg id="evi" viewBox="0 0 750 105"></svg></article><article class="card timeline"><h3>BSI mediano dos candidatos PPI</h3><svg id="bsi" viewBox="0 0 750 105"></svg></article><article class="card timeline"><h3>Desvio-padrão espacial do EVI</h3><svg id="evi-std" viewBox="0 0 750 105"></svg></article><article class="card timeline"><h3>Desvio-padrão espacial do BSI</h3><svg id="bsi-std" viewBox="0 0 750 105"></svg></article></section>
<section class="visual-layout"><article class="card combined"><h3>Comparação conjunta — escala global fixa: 0 a {maximum:.4f}</h3><svg id="combined" viewBox="0 0 700 500"></svg></article><section class="candidate-grid">{''.join(f'<article class="card"><h3 id="title{i}"></h3><svg id="plot{i}" viewBox="0 0 700 255"></svg></article>' for i in range(4))}</section></section></main>
<footer class="control-dock"><div class="dock-inner"><div class="review-row"><span class="review-title">Vegetação fotossinteticamente ativa</span><div id="options" class="checks"></div><button id="all">Todos</button><button id="none">Nenhum</button><span id="saved" class="saved"></span></div><div class="nav-row"><button id="prev">← Anterior</button><strong id="date"></strong><span id="counter" class="status"></span><button id="next">Próxima →</button><select id="jump"></select><button id="raw">Reflectância</button><button id="shape">Forma normalizada</button><button id="export">Exportar CSV</button><span id="qa" class="status"></span></div></div></footer>
<script>{_script(code, class_name, payload, bands, maximum)}</script></body></html>"""


def build_panels(
    root: str | Path | None = None,
    *,
    candidates: str | Path = "data/candidates",
    output: str | Path = "outputs/reproduced/panels",
    classes: list[str] | None = None,
) -> dict[str, Any]:
    repository, config = load_config(root)
    selected = select_classes(config, classes)
    candidate_dir = Path(candidates)
    output_dir = Path(output)
    if not candidate_dir.is_absolute():
        candidate_dir = repository / candidate_dir
    if not output_dir.is_absolute():
        output_dir = repository / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    maximum = 0.0
    for code in selected:
        data = pd.read_parquet(repository / "data" / "wtss" / f"wtss_class_{code}.parquet")
        valid = data[qa_valid(data, config)]
        maximum = max(maximum, float(np.nanmax(valid[config["bands"]].to_numpy(float))))

    counts: dict[str, int] = {}
    links: list[str] = []
    for code in selected:
        class_name = config["classes"][code]
        cand = pd.read_parquet(candidate_dir / f"candidates_class_{code}.parquet")
        manifest = pd.read_parquet(candidate_dir / f"ppi_manifest_class_{code}.parquet")
        data = pd.read_parquet(repository / "data" / "wtss" / f"wtss_class_{code}.parquet")
        data["date"] = pd.to_datetime(data["date"]).dt.strftime("%Y-%m-%d")
        payload: list[dict[str, Any]] = []
        available = manifest[pd.to_numeric(manifest["candidate_count"], errors="coerce").fillna(0).gt(0)].sort_values("date")
        for status in available.itertuples(index=False):
            valid = data[data["date"].eq(status.date)]
            valid = valid[qa_valid(valid, config)].sort_values("systematic_order").reset_index(drop=True)
            indices = np.unique(np.linspace(0, len(valid) - 1, min(128, len(valid)), dtype=np.int64))
            context = valid.iloc[indices][config["bands"]].to_numpy(float).tolist()
            mean = valid[config["bands"]].to_numpy(float).mean(axis=0).tolist()
            records = []
            for row in cand[cand["date"].eq(status.date)].sort_values("endmember_label").to_dict("records"):
                record = {"label": row["endmember_label"], "candidate_id": row["candidate_id"]}
                record.update({band: float(row[band]) for band in config["bands"]})
                records.append(record)
            warning = "" if status.status == "OK" else str(status.status)
            payload.append({"date": status.date, "valid_pixels": len(valid), "warning": warning, "candidates": records, "context": context, "mean": mean, **_indices(records)})
        (output_dir / f"class_{code}.html").write_text(_page(code, class_name, payload, config["bands"], maximum), encoding="utf-8")
        counts[code] = len(payload)
        links.append(f'<li><a href="class_{code}.html">Classe {code} — {html.escape(class_name)}</a> ({len(payload)} datas)</li>')
    index = f"<!doctype html><html lang='pt-BR'><meta charset='utf-8'><title>Painéis</title><style>{STYLE}</style><header><h1>Painéis de avaliação</h1></header><main><section class='card'><p>Selecione todos os candidatos compatíveis com vegetação fotossinteticamente ativa.</p><ul>{''.join(links)}</ul></section></main></html>"
    (output_dir / "index.html").write_text(index, encoding="utf-8")
    return {"output": str(output_dir), "classes": counts, "global_reflectance_max": maximum}
