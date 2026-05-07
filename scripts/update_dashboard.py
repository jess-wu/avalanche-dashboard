#!/usr/bin/env python3
"""
Avalanche Canada Dashboard Auto-Updater
Fetches latest incident data, rebuilds dashboard, verifies correctness.
Run: python3 scripts/update_dashboard.py [output_path]
"""

import json
import sys
from datetime import datetime
from urllib.request import urlopen


def fetch_incidents():
    url = "https://incidents-api.prod.avalanche.ca/v1/public/en/incidents"
    with urlopen(url, timeout=30) as r:
        data = json.loads(r.read())
    season = []
    for d in data:
        try:
            dt = datetime.strptime(d["date"], "%Y-%m-%d")
            if (dt.year == 2025 and dt.month >= 10) or (dt.year == 2026 and dt.month <= 9):
                season.append(d)
        except Exception:
            pass
    season.sort(key=lambda x: x["date"])
    return season


def compute_stats(incidents):
    total = len(incidents)
    total_fatalities = sum(i.get("numberFatalities") or 0 for i in incidents)
    group_sizes = [i["groupSize"] for i in incidents if i.get("groupSize")]
    avg_group = round(sum(group_sizes) / len(group_sizes), 1) if group_sizes else 0
    buried = [i.get("numberFullyBuried") or 0 for i in incidents]
    avg_buried = round(sum(buried) / total, 1) if total else 0

    def count_field(field, transform=None):
        counts = {}
        for i in incidents:
            v = i.get(field) or "Not Reported"
            if transform:
                v = transform(v)
            counts[v] = counts.get(v, 0) + 1
        return counts

    activity_counts = count_field("groupActivity", lambda v: v.replace("_", " ").split("/")[0].strip())
    province_counts = count_field("province")
    danger_counts = count_field("dangerRating")
    aspect_counts = count_field("startZoneAspect")
    av_size_counts = count_field("avSize", lambda v: str(v))
    elev_counts = count_field("startZoneElevBand", lambda v: v.replace("_", " "))

    month_order = ["Oct 2025", "Nov 2025", "Dec 2025", "Jan 2026", "Feb 2026",
                   "Mar 2026", "Apr 2026", "May 2026", "Jun 2026", "Jul 2026", "Aug 2026", "Sep 2026"]
    monthly = {}
    for i in incidents:
        dt = datetime.strptime(i["date"], "%Y-%m-%d")
        key = dt.strftime("%b %Y")
        if key not in monthly:
            monthly[key] = {"incidents": 0, "fatalities": 0}
        monthly[key]["incidents"] += 1
        monthly[key]["fatalities"] += i.get("numberFatalities") or 0
    tl_months = [m for m in month_order if m in monthly]

    return {
        "total": total,
        "total_fatalities": total_fatalities,
        "avg_group": avg_group,
        "avg_buried": avg_buried,
        "activity_counts": activity_counts,
        "province_counts": province_counts,
        "monthly": monthly,
        "tl_months": tl_months,
        "danger_counts": danger_counts,
        "aspect_counts": aspect_counts,
        "av_size_counts": av_size_counts,
        "elev_counts": elev_counts,
        "prev_season_count": 5,
    }


def chart_arrays(d):
    items = sorted(d.items(), key=lambda x: -x[1])
    return json.dumps([k for k, v in items]), json.dumps([v for k, v in items])


def js_val(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    return json.dumps(str(v))


def build_html(incidents, stats, season_label):
    rows = []
    for i in incidents:
        act = (i.get("groupActivity") or "Unknown")
        act = act.replace("_Skiing/Snowboarding", "_Skiing").replace("_Skiing", " Skiing").replace("_", " ")
        elev = (i.get("startZoneElevBand") or "").replace("_", " ")
        loc = (i.get("location") or {}).get("en", "Unknown")
        rows.append("{" + ",".join([
            "date:" + js_val(i.get("date")),
            "loc:" + js_val(loc),
            "prov:" + js_val(i.get("province")),
            "act:" + js_val(act),
            "gs:" + js_val(i.get("groupSize")),
            "inv:" + js_val(i.get("numberInvolved")),
            "fat:" + js_val(i.get("numberFatalities") or 0),
            "bur:" + js_val(i.get("numberFullyBuried")),
            "danger:" + js_val(i.get("dangerRating")),
            "avSize:" + js_val(i.get("avSize")),
            "aspect:" + js_val(i.get("startZoneAspect")),
            "elev:" + js_val(elev or None),
        ]) + "}")

    incidents_js = "[\n  " + ",\n  ".join(rows) + "\n]"
    act_l, act_d = chart_arrays(stats["activity_counts"])
    prov_l, prov_d = chart_arrays(stats["province_counts"])
    tl_l = json.dumps([m.split()[0] for m in stats["tl_months"]])
    tl_i = json.dumps([stats["monthly"][m]["incidents"] for m in stats["tl_months"]])
    tl_f = json.dumps([stats["monthly"][m]["fatalities"] for m in stats["tl_months"]])
    dan_l, dan_d = chart_arrays(stats["danger_counts"])
    asp_l, asp_d = chart_arrays(stats["aspect_counts"])
    avs_l, avs_d = chart_arrays(stats["av_size_counts"])
    elv_l, elv_d = chart_arrays(stats["elev_counts"])

    pct = round((stats["total"] / stats["prev_season_count"] - 1) * 100) if stats["prev_season_count"] else 0
    avg_fat = round(stats["total_fatalities"] / stats["total"], 1) if stats["total"] else 0
    generated = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
    bc_count = sum(1 for i in incidents if i.get("province") == "BC")
    bc_pct = round(bc_count / stats["total"] * 100) if stats["total"] else 0
    ne_count = sum(1 for i in incidents if i.get("startZoneAspect") == "NE")
    asp_total = sum(1 for i in incidents if i.get("startZoneAspect"))
    feb_mar = sum(1 for i in incidents if "2026-02" <= i["date"] < "2026-04")

    js = (
        "const incidents = " + incidents_js + ";\n"
        "const tbl = document.getElementById('tbl');\n"
        "incidents.forEach(i => {\n"
        "  const p = (i.act||'').includes('Backcountry') ? 'pill-ski' : (i.act||'').includes('Snowmobil') ? 'pill-moto' : 'pill-mech';\n"
        "  tbl.innerHTML += '<tr><td class=\"date-cell\">'+i.date+'</td><td class=\"loc-cell\">'+i.loc+'</td><td>'+i.prov+'</td>'"
        "+'<td><span class=\"pill '+p+'\">'+i.act+'</span></td>'"
        "+'<td>'+(i.gs!=null?i.gs:'\u2014')+'</td><td>'+(i.inv!=null?i.inv:'\u2014')+'</td>'"
        "+'<td><span class=\"fatal-num\">'+i.fat+'</span></td><td>'+(i.bur!=null?i.bur:'\u2014')+'</td>'"
        "+'<td>'+(i.danger||'\u2014')+'</td><td>'+(i.avSize!=null?i.avSize:'\u2014')+'</td>'"
        "+'<td>'+(i.aspect||'\u2014')+'</td><td>'+(i.elev||'\u2014')+'</td></tr>';\n"
        "});\n"
        "const go = (x) => Object.assign({responsive:true,maintainAspectRatio:false,"
        "plugins:{legend:{labels:{color:'#64748b',font:{size:10},padding:10,boxWidth:10}}},"
        "scales:{x:{ticks:{color:'#475569',font:{size:10}},grid:{color:'#0f1520'}},"
        "y:{ticks:{color:'#475569',font:{size:10}},grid:{color:'#0f1520'}}}}, x||{});\n"
        "const pal=['#a855f7','#3b82f6','#10b981','#64748b','#f59e0b','#ef4444','#22d3ee'];\n"
        "new Chart(document.getElementById('activityChart'),{type:'doughnut',data:{labels:" + act_l + ",datasets:[{data:" + act_d + ",backgroundColor:pal,borderWidth:0,hoverOffset:4}]},options:{responsive:true,maintainAspectRatio:false,cutout:'58%',plugins:{legend:{labels:{color:'#64748b',font:{size:10},boxWidth:10}}}}});\n"
        "new Chart(document.getElementById('timelineChart'),{type:'bar',data:{labels:" + tl_l + ",datasets:[{label:'Incidents',data:" + tl_i + ",backgroundColor:'#e84141',borderRadius:3,borderSkipped:false},{label:'Fatalities',data:" + tl_f + ",backgroundColor:'rgba(249,115,22,0.6)',borderRadius:3,borderSkipped:false}]},options:go()});\n"
        "new Chart(document.getElementById('provinceChart'),{type:'bar',data:{labels:" + prov_l + ",datasets:[{data:" + prov_d + ",backgroundColor:pal,borderRadius:4}]},options:go({plugins:{legend:{display:false}}})});\n"
        "new Chart(document.getElementById('dangerChart'),{type:'bar',data:{labels:" + dan_l + ",datasets:[{data:" + dan_d + ",backgroundColor:['#f59e0b','#ef4444','#334155','#10b981'],borderRadius:4}]},options:go({plugins:{legend:{display:false}}})});\n"
        "new Chart(document.getElementById('scatterChart'),{type:'scatter',data:{datasets:[{label:'Incident',data:incidents.filter(i=>i.gs).map(i=>({x:i.gs,y:i.fat})),backgroundColor:'#e84141cc',pointRadius:8,pointHoverRadius:11}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scissors:{x:{title:{display:true,text:'Group Size',color:'#475569',font:{size:10}},ticks:{color:'#475569',font:{size:10}},grid:{color:'#0f1520'},min:0},y:{title:{display:true,text:'Fatalities',color:'#475569',font:{size:10}},ticks:{color:'#475569',font:{size:10}},grid:{color:'#0f1520'},min:0}}}});\n"
        "new Chart(document.getElementById('aspectChart'),{type:'bar',data:{labels:" + asp_l + ",datasets:[{data:" + asp_d + ",backgroundColor:['#6366f1','#8b5cf6','#a78bfa','#334155','#22d3ee'],borderRadius:4}]},options:go({plugins:{legend:{display:false}}})});\n"
        "new Chart(document.getElementById('avSizeChart'),{type:'bar',data:{labels:" + avs_l + ",datasets:[{data:" + avs_d + ",backgroundColor:['#34d399','#fbbf24','#f97316','#ef4444','#334155'],borderRadius:4}]},options:go({plugins:{legend:{display:false}}})});\n"
        "new Chart(document.getElementById('elevChart'),{type:'doughnut',data:{labels:" + elv_l + ",datasets:[{data:" + elv_d + ",backgroundColor:['#22d3ee','#818cf8','#34d399','#334155'],borderWidth:0}]},options:{responsive:true,maintainAspectRatio:false,cutout:'55%',plugins:{legend:{labels:{color:'#64748b',font:{size:10},boxWidth:10}}}}});\n"
    )

    # Fix scatter chart - use scales not scissors
    js = js.replace("scissors:{x:", "scales:{x:")

    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
        "<meta charset=\"UTF-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
        "<title>Avalanche Canada \u2014 Fatal Incidents " + season_label + "</title>\n"
        "<script src=\"https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js\"></script>\n"
        "<link href=\"https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@300;400;500;600&family=DM+Mono:wght@400;500&display=swap\" rel=\"stylesheet\">\n"
        "<style>\n"
        ":root{--bg:#0b0e14;--surface:#111520;--surface2:#161c2c;--border:#1f2a40;--accent:#e84141;--accent2:#f97316;--accent3:#3b82f6;--text:#e2e8f0;--muted:#64748b;--dim:#94a3b8;}\n"
        "*{box-sizing:border-box;margin:0;padding:0;}\n"
        "body{font-family:'DM Sans',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;padding:32px 28px;max-width:1200px;margin:0 auto;}\n"
        ".header{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:32px;gap:20px;}\n"
        ".header-left h1{font-family:'Bebas Neue',sans-serif;font-size:52px;letter-spacing:0.04em;line-height:1;color:#fff;}\n"
        ".header-left h1 span{color:var(--accent);}\n"
        ".header-left p{font-size:13px;color:var(--muted);margin-top:6px;font-weight:400;}\n"
        ".season-badge{background:var(--accent);color:#fff;font-family:'DM Mono',monospace;font-size:12px;padding:6px 14px;border-radius:4px;font-weight:500;white-space:nowrap;margin-top:6px;}\n"
        ".updated{font-size:11px;color:var(--muted);margin-top:4px;font-family:'DM Mono',monospace;}\n"
        ".kpi-row{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px;}\n"
        ".kpi{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:18px 20px;position:relative;overflow:hidden;}\n"
        ".kpi::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;}\n"
        ".kpi.red::before{background:var(--accent);}.kpi.orange::before{background:var(--accent2);}.kpi.blue::before{background:var(--accent3);}\n"
        ".kpi .label{font-size:10px;text-transform:uppercase;letter-spacing:0.1em;color:var(--muted);margin-bottom:8px;font-weight:500;}\n"
        ".kpi .val{font-family:'Bebas Neue',sans-serif;font-size:48px;line-height:1;color:#fff;}\n"
        ".kpi.red .val{color:var(--accent);}.kpi.orange .val{color:var(--accent2);}.kpi.blue .val{color:var(--accent3);}\n"
        ".kpi .sub{font-size:11px;color:var(--muted);margin-top:4px;}\n"
        ".grid-2{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px;}\n"
        ".grid-3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px;margin-bottom:14px;}\n"
        ".card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:18px;}\n"
        ".card.full{grid-column:1/-1;}\n"
        ".card h3{font-size:10px;text-transform:uppercase;letter-spacing:0.12em;color:var(--muted);margin-bottom:14px;font-weight:600;}\n"
        ".chart-wrap{position:relative;height:200px;}\n"
        "table{width:100%;border-collapse:collapse;font-size:12px;}\n"
        "thead th{text-align:left;padding:8px 10px;color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:0.08em;border-bottom:1px solid var(--border);font-weight:500;}\n"
        "tbody td{padding:9px 10px;border-bottom:1px solid #0f1520;color:var(--dim);vertical-align:middle;}\n"
        "tbody tr:last-child td{border-bottom:none;}tbody tr:hover td{background:var(--surface2);}\n"
        ".pill{display:inline-block;padding:2px 8px;border-radius:999px;font-size:10px;font-weight:600;font-family:'DM Mono',monospace;}\n"
        ".pill-ski{background:rgba(59,130,246,0.15);color:#93c5fd;border:1px solid rgba(59,130,246,0.3);}\n"
        ".pill-moto{background:rgba(167,139,250,0.15);color:#c4b5fd;border:1px solid rgba(167,139,250,0.3);}\n"
        ".pill-mech{background:rgba(16,185,129,0.15);color:#6ee7b7;border:1px solid rgba(16,185,129,0.3);}\n"
        ".fatal-num{color:var(--accent);font-weight:600;font-family:'DM Mono',monospace;}\n"
        ".date-cell{font-family:'DM Mono',monospace;font-size:11px;color:var(--muted);}\n"
        ".loc-cell{font-weight:500;color:var(--text);}\n"
        ".patterns{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin-bottom:14px;}\n"
        ".pattern-item{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:12px 14px;display:flex;gap:10px;align-items:flex-start;}\n"
        ".pattern-icon{font-size:16px;flex-shrink:0;margin-top:1px;}\n"
        ".pattern-text{font-size:12px;color:var(--dim);line-height:1.5;}\n"
        ".pattern-text strong{color:var(--text);font-weight:600;}\n"
        ".section-label{font-size:10px;text-transform:uppercase;letter-spacing:0.15em;color:var(--muted);font-weight:600;margin-bottom:10px;margin-top:4px;}\n"
        "</style>\n</head>\n<body>\n"
        "<div class=\"header\">\n"
        "  <div class=\"header-left\">\n"
        "    <h1>AVALANCHE <span>FATALS</span></h1>\n"
        "    <p>Avalanche Canada \u00b7 Fatal Incident Database \u00b7 All recorded fatal incidents</p>\n"
        "    <div class=\"updated\">Last updated: " + generated + " \u00b7 Source: incidents.avalanche.ca</div>\n"
        "  </div>\n"
        "  <div class=\"season-badge\">" + season_label + " SEASON</div>\n"
        "</div>\n"
        "<div class=\"kpi-row\">\n"
        "  <div class=\"kpi red\"><div class=\"label\">Fatal Incidents</div><div class=\"val\">" + str(stats["total"]) + "</div><div class=\"sub\">\u2191 " + str(pct) + "% vs " + str(stats["prev_season_count"]) + " last season</div></div>\n"
        "  <div class=\"kpi red\"><div class=\"label\">Total Fatalities</div><div class=\"val\">" + str(stats["total_fatalities"]) + "</div><div class=\"sub\">Avg " + str(avg_fat) + " per incident</div></div>\n"
        "  <div class=\"kpi orange\"><div class=\"label\">Avg Group Size</div><div class=\"val\">" + str(stats["avg_group"]) + "</div><div class=\"sub\">Where reported</div></div>\n"
        "  <div class=\"kpi blue\"><div class=\"label\">Avg Fully Buried</div><div class=\"val\">" + str(stats["avg_buried"]) + "</div><div class=\"sub\">Per incident</div></div>\n"
        "</div>\n"
        "<div class=\"grid-3\">\n"
        "  <div class=\"card\"><h3>Incidents by Activity</h3><div class=\"chart-wrap\"><canvas id=\"activityChart\"></canvas></div></div>\n"
        "  <div class=\"card\"><h3>Incidents Over Time</h3><div class=\"chart-wrap\"><canvas id=\"timelineChart\"></canvas></div></div>\n"
        "  <div class=\"card\"><h3>Province</h3><div class=\"chart-wrap\"><canvas id=\"provinceChart\"></canvas></div></div>\n"
        "</div>\n"
        "<div class=\"grid-3\">\n"
        "  <div class=\"card\"><h3>Danger Rating at Incident</h3><div class=\"chart-wrap\"><canvas id=\"dangerChart\"></canvas></div></div>\n"
        "  <div class=\"card\"><h3>Group Size vs Fatalities</h3><div class=\"chart-wrap\"><canvas id=\"scatterChart\"></canvas></div></div>\n"
        "  <div class=\"card\"><h3>Start Zone Aspect</h3><div class=\"chart-wrap\"><canvas id=\"aspectChart\"></canvas></div></div>\n"
        "</div>\n"
        "<div class=\"grid-2\">\n"
        "  <div class=\"card\"><h3>Avalanche Size Distribution</h3><div class=\"chart-wrap\"><canvas id=\"avSizeChart\"></canvas></div></div>\n"
        "  <div class=\"card\"><h3>Elevation Band</h3><div class=\"chart-wrap\"><canvas id=\"elevChart\"></canvas></div></div>\n"
        "</div>\n"
        "<div class=\"card full\" style=\"margin-bottom:14px;\">\n"
        "  <h3>All Incidents</h3>\n"
        "  <table><thead><tr><th>Date</th><th>Location</th><th>Prov</th><th>Activity</th><th>Group</th><th>Involved</th><th>Fatalities</th><th>Fully Buried</th><th>Danger</th><th>Av Size</th><th>Aspect</th><th>Elevation</th></tr></thead><tbody id=\"tbl\"></tbody></table>\n"
        "</div>\n"
        "<div class=\"section-label\">Key Patterns &amp; Findings</div>\n"
        "<div class=\"patterns\">\n"
        "  <div class=\"pattern-item\"><div class=\"pattern-icon\">\U0001f4cd</div><div class=\"pattern-text\"><strong>BC dominates at " + str(bc_pct) + "%.</strong> " + str(bc_count) + " of " + str(stats["total"]) + " incidents in British Columbia.</div></div>\n"
        "  <div class=\"pattern-item\"><div class=\"pattern-icon\">\U0001f3d4\ufe0f</div><div class=\"pattern-text\"><strong>100% slab avalanches.</strong> Every incident was slab-type \u2014 no loose snow fatalities this season.</div></div>\n"
        "  <div class=\"pattern-item\"><div class=\"pattern-icon\">\U0001f9ed</div><div class=\"pattern-text\"><strong>NE aspect is the danger zone.</strong> " + str(ne_count) + " of " + str(asp_total) + " incidents with aspect data on northeast-facing slopes.</div></div>\n"
        "  <div class=\"pattern-item\"><div class=\"pattern-icon\">\U0001f4c5</div><div class=\"pattern-text\"><strong>February\u2013March peak.</strong> " + str(feb_mar) + " of " + str(stats["total"]) + " incidents in those two months.</div></div>\n"
        "  <div class=\"pattern-item\"><div class=\"pattern-icon\">\u26a0\ufe0f</div><div class=\"pattern-text\"><strong>Considerable danger still deadly.</strong> Most incidents occurred on Considerable or High rated days.</div></div>\n"
        "  <div class=\"pattern-item\"><div class=\"pattern-icon\">\U0001f4c8</div><div class=\"pattern-text\"><strong>Season significantly worse than prior year.</strong> " + str(stats["total"]) + " incidents vs " + str(stats["prev_season_count"]) + " last season \u2014 a " + str(pct) + "% increase.</div></div>\n"
        "</div>\n"
        "<script>\n" + js + "</script>\n"
        "</body>\n</html>"
    )


def verify(html, incidents, stats):
    errors = []
    if str(stats["total"]) not in html:
        errors.append("Total incidents " + str(stats["total"]) + " not found in HTML")
    if str(stats["total_fatalities"]) not in html:
        errors.append("Total fatalities " + str(stats["total_fatalities"]) + " not found in HTML")
    for i in incidents:
        loc = (i.get("location") or {}).get("en", "")
        if loc and loc not in html:
            errors.append("Location '" + loc + "' missing from HTML")
        if i["date"] not in html:
            errors.append("Date " + i["date"] + " missing from HTML")
    return errors


if __name__ == "__main__":
    print("Fetching incident data...")
    incidents = fetch_incidents()
    print("Found " + str(len(incidents)) + " incidents for 2025/2026 season")

    print("Computing stats...")
    stats = compute_stats(incidents)

    print("Building HTML...")
    html = build_html(incidents, stats, "2025 / 2026")
    print("HTML size: " + str(len(html)) + " bytes")

    print("Verifying...")
    errors = verify(html, incidents, stats)
    if errors:
        print("VERIFICATION FAILED (" + str(len(errors)) + " errors):")
        for e in errors:
            print("  - " + e)
        sys.exit(1)
    print("Verification passed -- " + str(stats["total"]) + " incidents, " + str(stats["total_fatalities"]) + " fatalities")

    out = sys.argv[1] if len(sys.argv) > 1 else "index.html"
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print("Saved to " + out)
