# app.py — Points (500 m snap-to-centroid) + Community (RD/LG/FN) + Legend toggles + Click halo + Readme
# - 500 m snap-to-centroid (deterministic; no jitter/offset UI)
# - Halo highlight of clicked set (clears/replaced on next click)
# - Legend: extent buckets with in-view counts + RD/LG/FN line toggles
# - Data tab: All rows (no in-view option)
# - No auto-fit on filter changes; initial re-zoom minimized
# - Readme tab: deliverables summary + key terms + Sendai priorities + optional logos

from shiny import App, ui, render, reactive
from shinywidgets import output_widget, render_widget
from ipyleaflet import Map, TileLayer, ScaleControl, GeoJSON, LayersControl, WidgetControl
from ipywidgets import Layout, VBox, HBox, HTML, Checkbox
from pathlib import Path
import json, html, math, statistics, collections, base64, mimetypes


# ---------- CONFIG ----------
POINTS_FILENAME     = "WGSpoints.geojson"
COMMUNITY_FILENAME  = "community_boundaries.geojson"   # has 'Type' in {"RD","LG","FN"}

OSM_URL  = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
OSM_ATTR = "© OpenStreetMap contributors"

DEFAULT_CLIP_PAD_DEG  = 0.25
DEFAULT_VERTEX_STRIDE = 3

EXTENT_ORDER  = ["Site-specific", "Community", "Sub-regional", "Regional and broader"]
EXTENT_RADIUS = {"Site-specific":5, "Community":7, "Sub-regional":9, "Regional and broader":11}
EXTENT_COLOR  = {
    "Site-specific":        "#1f6feb",
    "Community":            "#10b981",
    "Sub-regional":         "#f59e0b",
    "Regional and broader": "#7c3aed",   # <- as requested
}
COMM_TYPE_FIELD = "Type"  # "RD", "LG" or "FN"

# Snap distance (meters)
CLUSTER_DIST_M     = 500.0

# Internal defaults for map display (since controls are hidden)
SHOW_COMMUNITY_DEFAULT   = True
EXACT_BOUNDS_DEFAULT     = True
LINE_WIDTH_COMM_DEFAULT  = 4.0
CLIP_PAD_DEFAULT         = DEFAULT_CLIP_PAD_DEG
STRIDE_DEFAULT           = DEFAULT_VERTEX_STRIDE

FILTER_FIELDS = [
    "Does the Study Outcome Aim to Reduce Risk? (Y/N)",
    "Reduce Hazard (Y/N)",
    "Reduce Exposure (Y/N)",
    "Reduce Vulnerability (Y/N)",
    "Build Resilience (Y/N)",
    "Does the Study Outcome Aim to Provide Ecosystem Services? (Y/N)",
    "How Does the Project Outcome Aim to Provide Ecosystem Services?",
]

AIM_FILTER_CHOICES = {
    "reduce_risk": "Reduce Risk",
    "reduce_hazard": "Reduce Hazard",
    "reduce_exposure": "Reduce Exposure",
    "reduce_vulnerability": "Reduce Vulnerability",
    "build_resilience": "Build Resilience",
    "provide_ecosystem_services": "Provide Ecosystem Services",
}

AIM_FILTER_FIELDS = {
    "reduce_risk": "Does the Study Outcome Aim to Reduce Risk? (Y/N)",
    "reduce_hazard": "Reduce Hazard (Y/N)",
    "reduce_exposure": "Reduce Exposure (Y/N)",
    "reduce_vulnerability": "Reduce Vulnerability (Y/N)",
    "build_resilience": "Build Resilience (Y/N)",
    "provide_ecosystem_services": "Does the Study Outcome Aim to Provide Ecosystem Services? (Y/N)",
}

# Community boundary line colours (legend + layers)
COMM_LINE_COLORS = {
    "RD": "#A9A9A9",   # <- RD as requested
    "LG": "#374151",
    "FN": "#f97316",
}


# ---------- helpers (IO/coords) ----------
def _candidates(name: str):
    base = Path(__file__).parent
    return [
        base / "data" / name,
        base / "www" / "data" / name,
        Path.cwd() / "data" / name,
        Path.cwd() / "www" / "data" / name,
    ]


def _read_json_any(paths):
    for p in paths:
        try:
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def _to_float(x):
    try:
        return float(x)
    except Exception:
        return None


def _finite_latlon(lat, lon):
    if lat is None or lon is None:
        return False
    try:
        if math.isnan(lat) or math.isnan(lon):
            return False
    except Exception:
        pass
    return -90 <= lat <= 90 and -180 <= lon <= 180


def _load_points_records():
    gj = _read_json_any(_candidates(POINTS_FILENAME))
    if gj is None:
        raise FileNotFoundError(f"{POINTS_FILENAME} not found in ./data or ./www/data")
    out, idx = [], 0
    for feat in gj.get("features", []):
        geom = feat.get("geometry") or {}
        props = feat.get("properties") or {}
        t = geom.get("type")
        if t == "Point":
            lon, lat = (geom.get("coordinates") or [None, None])[:2]
            lat, lon = _to_float(lat), _to_float(lon)
            if _finite_latlon(lat, lon):
                out.append({"id": idx, "lat": lat, "lon": lon, "props": props}); idx += 1
        elif t == "MultiPoint":
            for c in geom.get("coordinates") or []:
                lon, lat = (c[:2] + [None, None])[:2]
                lat, lon = _to_float(lat), _to_float(lon)
                if _finite_latlon(lat, lon):
                    out.append({"id": idx, "lat": lat, "lon": lon, "props": props}); idx += 1
    return out


def _build_key_order(items):
    order, seen = [], set()
    if items:
        for k in (items[0].get("props") or {}).keys():
            order.append(k); seen.add(k)
    for it in items:
        for k in (it.get("props") or {}).keys():
            if k not in seen:
                order.append(k); seen.add(k)
    return order


def _points_centroid(items):
    if not items:
        return (49.2827, -123.1207, 9)
    lats = [it["lat"] for it in items]
    lons = [it["lon"] for it in items]
    return (sum(lats)/len(lats), sum(lons)/len(lons), 9)


def _points_bbox(items):
    if not items:
        return (49.0, -123.6, 49.6, -122.2)
    lats = [it["lat"] for it in items]
    lons = [it["lon"] for it in items]
    return (min(lats), min(lons), max(lats), max(lons))


# ---------- extent normalization (4 buckets only) ----------
def _canon_extent(x: str):
    if x is None:
        return "Regional and broader"
    s = str(x).strip().lower()
    if not s:
        return "Regional and broader"
    if s in {"site-specific","site specifc","site specifc.","site"}:
        return "Site-specific"
    if s in {"community","community-level","community level"}:
        return "Community"
    if s in {"sub-regional","subregional","sub region","sub region al"}:
        return "Sub-regional"
    if s in {
        "regional","region","boarder","broader","border",
        "regional and boarder","regional & boarder","regional and broader"
    }:
        return "Regional and broader"
    return "Regional and broader"


# ---------- distances / snapping ----------
def _haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1 = math.radians(lat1); p2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dlmb/2)**2
    return 2*R*math.asin(math.sqrt(a))


def _cluster_and_snap(points, tol_m=CLUSTER_DIST_M):
    """Snap every point to the centroid of its <=tol_m cluster (no jitter)."""
    if not points:
        return {}
    groups = []
    for it in points:
        lat = it["lat"]; lon = it["lon"]
        matched = None
        for g in groups:
            if _haversine_m(lat, lon, g["lat"], g["lon"]) <= tol_m:
                g["members"].append(it)
                n = len(g["members"])
                g["lat"] += (lat - g["lat"]) / n
                g["lon"] += (lon - g["lon"]) / n
                matched = g
                break
        if matched is None:
            groups.append({"lat": lat, "lon": lon, "members": [it]})
    id2disp = {}
    for g in groups:
        cy, cx = g["lat"], g["lon"]
        for m in g["members"]:
            id2disp[m["id"]] = (cy, cx)
    return id2disp


# ---------- polygon→polyline helpers ----------
def _swap_lonlat_if_needed(sample_lon, sample_lat):
    if not sample_lon or not sample_lat:
        return False
    lon_abs = [abs(x) for x in sample_lon if x is not None]
    lat_abs = [abs(y) for y in sample_lat if y is not None]
    if not lon_abs or not lat_abs:
        return False
    lon_med = statistics.median(lon_abs); lat_med = statistics.median(lat_abs)
    return lon_med < 70 and lat_med > 80


def _collect_lonlat_samples(gj, max_n=5000):
    lons, lats = [], []
    if not gj or gj.get("type") != "FeatureCollection":
        return lons, lats
    count = 0
    for f in gj.get("features", []):
        g = f.get("geometry") or {}
        t = g.get("type"); c = g.get("coordinates")
        if t == "MultiPolygon":
            for poly in (c or []):
                for ring in (poly or []):
                    for p in (ring or []):
                        if isinstance(p,(list,tuple)) and len(p)>=2:
                            lons.append(_to_float(p[0])); lats.append(_to_float(p[1])); count += 1
                            if count >= max_n:
                                return lons, lats
        elif t == "Polygon":
            for ring in (c or []):
                for p in (ring or []):
                    if isinstance(p,(list,tuple)) and len(p)>=2:
                        lons.append(_to_float(p[0])); lats.append(_to_float(p[1])); count += 1
                        if count >= max_n:
                            return lons, lats
        elif t in ("LineString","MultiLineString"):
            seqs = [c] if t == "LineString" else c
            for ln in (seqs or []):
                for p in (ln or []):
                    if isinstance(p,(list,tuple)) and len(p)>=2:
                        lons.append(_to_float(p[0])); lats.append(_to_float(p[1])); count += 1
                        if count >= max_n:
                            return lons, lats
    return lons, lats


def _poly_exact_to_lines_feature(f, swap, close=True):
    g = f.get("geometry") or {}
    t = g.get("type")
    coords = g.get("coordinates") or []
    def conv(p):
        if not (isinstance(p,(list,tuple)) and len(p)>=2):
            return None
        lon, lat = _to_float(p[0]), _to_float(p[1])
        if swap:
            lon, lat = lat, lon
        return [lon, lat] if _finite_latlon(lat, lon) else None
    lines = []
    if t == "Polygon":
        for ring in (coords or []):
            acc = [q for p in (ring or []) if (q:=conv(p))]
            if close and len(acc)>=2 and acc[0]!=acc[-1]:
                acc.append(acc[0])
            if len(acc)>=2:
                lines.append(acc)
    elif t == "MultiPolygon":
        for poly in (coords or []):
            for ring in (poly or []):
                acc = [q for p in (ring or []) if (q:=conv(p))]
                if close and len(acc)>=2 and acc[0]!=acc[-1]:
                    acc.append(acc[0])
                if len(acc)>=2:
                    lines.append(acc)
    else:
        return None
    if not lines:
        return None
    return {
        "type":"Feature",
        "properties": f.get("properties") or {},
        "geometry": {"type":"MultiLineString","coordinates":lines},
    }


def _clip_bbox(lat, lon, bbox):
    s, w, n, e = bbox
    return (s <= lat <= n) and (w <= lon <= e)


def _poly_thinclip_to_lines_feature(f, swap, bbox, pad_deg, stride, close=True):
    g = f.get("geometry") or {}
    t = g.get("type")
    coords = g.get("coordinates") or []
    south, west, north, east = bbox
    pad_bbox = (south-pad_deg, west-pad_deg, north+pad_deg, east+pad_deg)

    def conv(p):
        if not (isinstance(p,(list,tuple)) and len(p)>=2):
            return None
        lon, lat = _to_float(p[0]), _to_float(p[1])
        if swap:
            lon, lat = lat, lon
        return [lon, lat] if _finite_latlon(lat, lon) else None

    lines = []
    if t == "Polygon":
        for ring in (coords or []):
            acc = []
            for i, p in enumerate(ring or []):
                q = conv(p)
                if not q:
                    continue
                if i == 0 or (stride <= 1) or (i % stride == 0):
                    if _clip_bbox(q[1], q[0], pad_bbox):
                        acc.append(q)
            if close and len(acc)>=2 and acc[0] != acc[-1]:
                acc.append(acc[0])
            if len(acc)>=2:
                lines.append(acc)
    elif t == "MultiPolygon":
        for poly in (coords or []):
            for ring in (poly or []):
                acc = []
                for i, p in enumerate(ring or []):
                    q = conv(p)
                    if not q:
                        continue
                    if i == 0 or (stride <= 1) or (i % stride == 0):
                        if _clip_bbox(q[1], q[0], pad_bbox):
                            acc.append(q)
                if close and len(acc)>=2 and acc[0] != acc[-1]:
                    acc.append(acc[0])
                if len(acc)>=2:
                    lines.append(acc)
    else:
        return None

    if not lines:
        return None
    return {
        "type": "Feature",
        "properties": f.get("properties") or {},
        "geometry": {"type": "MultiLineString", "coordinates": lines},
    }


def _sanitize_bounds_to_lines(raw_gj, pts_bbox, pad_deg, stride, exact=False):
    if not raw_gj or raw_gj.get("type") != "FeatureCollection":
        return None, {"features": 0, "types": {}, "swap": False}
    sample_lons, sample_lats = _collect_lonlat_samples(raw_gj)
    swap = _swap_lonlat_if_needed(sample_lons, sample_lats)
    out = {"type":"FeatureCollection","features":[]}
    type_counts = collections.Counter()
    south, west, north, east = pts_bbox
    for f in raw_gj.get("features", []):
        g = f.get("geometry") or {}; t = g.get("type")
        type_counts[t or "None"] += 1
        if t in ("Polygon","MultiPolygon"):
            feat = _poly_exact_to_lines_feature(f, swap) if exact else \
                   _poly_thinclip_to_lines_feature(
                       f, swap, (south,west,north,east), pad_deg, max(1,int(stride))
                   )
            if feat:
                out["features"].append(feat)
        elif t in ("LineString","MultiLineString"):
            coords = g.get("coordinates") or []
            seqs = [coords] if t == "LineString" else coords
            parts = []
            for ln in (seqs or []):
                acc = []
                for i, p in enumerate(ln or []):
                    if not (isinstance(p,(list,tuple)) and len(p)>=2):
                        continue
                    lon, lat = _to_float(p[0]), _to_float(p[1])
                    if swap:
                        lon, lat = lat, lon
                    if not _finite_latlon(lat, lon):
                        continue
                    if exact:
                        acc.append([lon, lat])
                    else:
                        if i == 0 or (int(stride) <= 1) or (i % stride == 0):
                            if _clip_bbox(lat, lon, (south-pad_deg,west-pad_deg,north+pad_deg,east+pad_deg)):
                                acc.append([lon, lat])
                if len(acc) >= 2:
                    parts.append(acc)
            if parts:
                out["features"].append({
                    "type":"Feature",
                    "properties": f.get("properties") or {},
                    "geometry": {"type": t, "coordinates": (parts if t=="MultiLineString" else parts[0])},
                })
    meta = {"features": len(out["features"]), "types": dict(type_counts), "swap": swap}
    return (out if out["features"] else None), meta


# ---------- DATA (load once) ----------
ALL_POINTS = _load_points_records()
KEY_ORDER  = _build_key_order(ALL_POINTS)
PTS_BBOX   = _points_bbox(ALL_POINTS)
RAW_COMMUNITY = _read_json_any(_candidates(COMMUNITY_FILENAME))

# Safe default bounds [[s,w],[n,e]]
BOUNDS_DEFAULT = [[PTS_BBOX[0], PTS_BBOX[1]], [PTS_BBOX[2], PTS_BBOX[3]]]

# Precompute SNAP display coords once (500 m centroid snapping)
ID2DISP_SNAP = _cluster_and_snap(ALL_POINTS, tol_m=CLUSTER_DIST_M)


# ---------- find fields ----------
def _find_field(name_exact: str, contains_ok=True):
    target = name_exact.strip().lower()
    for k in KEY_ORDER:
        if k.strip().lower() == target:
            return k
    if contains_ok:
        for k in KEY_ORDER:
            if target in k.strip().lower():
                return k
    return None


EXTENT_FIELD   = _find_field("Project extent")
ECO_YN_FIELD   = _find_field("Does the Study Outcome Aim to Provide Ecosystem Services? (Y/N)")
ECO_HOW_FIELD  = _find_field("How Does the Project Outcome Aim to Provide Ecosystem Services?")

# Fields that should NOT show in column picker or tables.
ALWAYS_HIDDEN_FIELD_NAMES = {
    "fid",
    "project id",
    "year of commencement",
    "created by",
    "date created",
    "modified by",
    "date modified",
}
HIDDEN_FIELDS = {k for k in KEY_ORDER if k.strip().lower() in ALWAYS_HIDDEN_FIELD_NAMES}

# Default checked fields in the "Fields to show" selector.
DEFAULT_SELECTED_FIELDS = [
    "Project Name",
    "Project Proponent/Owner",
    "Year of Completion",
    "Project Goals",
    "Most Prominent Hazards",
    "Sendai Priority",
]


# ----- README helpers -----
LOGO_DIR = Path(__file__).parent / "www" / "logos"


def deliverables_rows():
    return [
        {
            "Deliverable": "1. Structured Excel database",
            "Function": "Compiles and categorizes relevant projects in the region",
            "Intended Purpose": "Can be used to easily update existing, or add new project information by a non-technical user.",
            "Intended Users": "Non-technical practitioners",
        },
        {
            "Deliverable": "2. Geospatial database",
            "Function": "Links the information from the Excel database with GIS, enabling spatial visualization and querying",
            "Intended Purpose": "Add geospatial components to updated or new projects added in the Excel database.",
            "Intended Users": "Users with minimum GIS skills",
        },
        {
            "Deliverable": "3. HTML dashboard",
            "Function": "Can be deployed online for general use",
            "Intended Purpose": "Can be used by anybody to search projects by keywords, or spatially.",
            "Intended Users": "Non-technical practitioners including the public",
        },
    ]


def html_table_from_rows(rows, columns):
    """HTML table for Readme deliverables (fixed so all rows show)."""
    thead = "".join(
        f"<th style='text-align:left; padding:8px 10px; border-bottom:2px solid #ccc'>{html.escape(col)}</th>"
        for col in columns
    )
    tb_rows = []
    for r in rows:
        tds = "".join(
            f"<td style='padding:8px 10px; vertical-align:top'>{html.escape(str(r.get(col, '')))}</td>"
            for col in columns
        )
        tb_rows.append(f"<tr>{tds}</tr>")
    return (
        "<table style='border-collapse:collapse; width:100%; font-size:14px; margin-top:10px'>"
        f"<thead><tr>{thead}</tr></thead><tbody>{''.join(tb_rows)}</tbody></table>"
    )


def logo_files_to_data_uris():
    items = []
    if LOGO_DIR.exists() and LOGO_DIR.is_dir():
        for p in sorted(LOGO_DIR.iterdir()):
            if not p.is_file():
                continue
            ext = p.suffix.lower()
            if ext not in {".png", ".jpg", ".jpeg", ".svg", ".webp"}:
                continue
            mime, _ = mimetypes.guess_type(p.name)
            if mime is None:
                if ext == ".svg":
                    mime = "image/svg+xml"
                elif ext == ".webp":
                    mime = "image/webp"
                elif ext in {".jpg", ".jpeg"}:
                    mime = "image/jpeg"
                else:
                    mime = "image/png"
            try:
                if ext == ".svg":
                    raw = p.read_text(encoding="utf-8")
                    b64 = base64.b64encode(raw.encode("utf-8")).decode("ascii")
                else:
                    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
                items.append({"name": p.name, "data_uri": f"data:{mime};base64,{b64}"})
            except Exception:
                continue
    return items


# ---------- UI ----------
app_ui = ui.page_sidebar(
    # Sidebar
    ui.sidebar(
        ui.h5("Filters"),
        ui.input_selectize(
            "f_aims",
            "Study Outcome Aims",
            choices=AIM_FILTER_CHOICES,
            selected=[],
            multiple=True,
        ),
        ui.output_ui("ecos_how_filter"),
        ui.tags.hr(style="border:0;border-top:2px solid #8a93a1;margin:12px 0 10px 0"),
        ui.div("Fields to show", {"style":"font-weight:700;color:#111827;margin:0 0 6px 0"}),
        ui.output_ui("col_picker"),
        width="340px",
    ),

    # Global CSS
    ui.tags.style(
        """
    .leaflet-control { z-index: 10000 !important; }
    .leaflet-top .leaflet-control { margin-top: 8px; }
    .leaflet-zoom-animated, .leaflet-zoom-anim { transition: none !important; animation: none !important; }
    .leaflet-fade-anim { transition: none !important; }

    .leaflet-control .widget-box,
    .leaflet-control .jupyter-widgets,
    .leaflet-control .widget-container,
    .leaflet-control .widget-inline-hbox,
    .leaflet-control .widget-vbox,
    .leaflet-control .widget-hbox,
    .leaflet-control .p-Widget,
    .leaflet-control .lm-Widget {
        overflow: visible !important; max-height: none !important;
    }
    .leaflet-control .widget-vbox > div { overflow: visible !important; }
    .leaflet-control .jupyter-widgets, .leaflet-control .widget-box { scrollbar-width: none !important; }
    .leaflet-control .jupyter-widgets::-webkit-scrollbar,
    .leaflet-control .p-Widget::-webkit-scrollbar,
    .leaflet-control .lm-Widget::-webkit-scrollbar { display: none !important; }
    .readme p { margin: 0 0 10px 0; }
    .logo-cap { margin:6px 0 0 0; font-size:12px; opacity:.7 }
    .leaflet-control-layers { display: none !important; }

    /* Sticky header + pinned first column for data tables */
    .sticky-wrap { overflow: auto; }
    table.sticky { border-collapse: separate; border-spacing: 0; }
    table.sticky thead th {
      position: sticky; top: 0; background: #f8fafc;
      z-index: 2; box-shadow: inset 0 -1px 0 #e5e7eb;
    }
    table.sticky td:first-child,
    table.sticky th:first-child {
      position: sticky; left: 0; background: #ffffff;
      z-index: 1; box-shadow: inset -1px 0 0 #f1f5f9;
    }
    table.sticky thead th:first-child { z-index: 3; }
    """
    ),

    # Main content
    ui.navset_tab(
        ui.nav_panel(
            "Map",
            output_widget("m", height="60vh"),
            ui.tags.div(
                ui.HTML("<div style='font-weight:600;margin:8px 0 6px 0'>Selected projects</div>"),
                ui.output_ui("clicked_table"),
                style="margin-top:6px",
            ),
        ),
        ui.nav_panel(
            "Data",
            ui.layout_columns(
                ui.input_text("data_search", "Search (all attributes)", placeholder="Type to filter (case-insensitive)"),
                col_widths=(12,),
            ),
            ui.output_ui("table_data"),
        ),
        ui.nav_panel(
            "Readme",
            ui.div(
                {"class":"readme","style":"padding:16px; line-height:1.55; max-width:980px"},
                ui.h3("About the Database and Tools"),
                ui.p(
                    "This dashboard is part of a three-deliverable toolset developed to support "
                    "risk-related project compilation, spatial visualization, and online dissemination "
                    "for the Mainland Coast Salish Area."
                ),
                ui.p(
                    "Use the Map tab to explore locations, and the Data tab to search/filter the database. "
                    "The summary below outlines the three deliverables, including function, purpose, and audience."
                ),
                ui.output_ui("readme_table"),

                ui.tags.hr(style="margin:20px 0; border-top:2px solid #ddd"),

                ui.h3("Key Terms"),
                ui.p(
                    ui.HTML(
                        "<b>Risk</b> is the potential loss of life, injury, or damage that could occur to a community or system. "
                        "<b>Risk</b> depends on three factors: "
                        "<b>hazard</b> (a natural event or process that can cause harm), "
                        "<b>exposure</b> (people, assets, or ecosystems that could be affected), and "
                        "<b>vulnerability</b> (how easily those exposed elements can be harmed)."
                    )
                ),
                ui.p(
                    ui.HTML(
                        "<b>Resilience</b> is the ability of a community or system to resist, absorb, adapt to, "
                        "and recover from hazards efficiently, while maintaining essential functions."
                    )
                ),
                ui.p(
                    ui.HTML(
                        "<b>Ecosystem services</b> are the benefits that healthy ecosystems provide to people—such as clean water, "
                        "flood regulation, and cultural value. These principles are reflected in <i>Hílekw Sq’eq’ó</i> and "
                        "Ducks Unlimited’s <i>International Science Report 2025</i>, which emphasize conserving and strengthening "
                        "natural systems for long-term resilience."
                    )
                ),

                ui.h3("The Sendai Priorities"),
                ui.p("According to the Sendai Framework for Disaster Risk Reduction (2015–2030):"),
                ui.tags.ul(
                    ui.tags.li(ui.HTML("<b>Priority 1:</b> Understanding disaster risk.")),
                    ui.tags.li(ui.HTML("<b>Priority 2:</b> Strengthening disaster risk governance to manage disaster risk.")),
                    ui.tags.li(ui.HTML("<b>Priority 3:</b> Investing in disaster reduction for resilience.")),
                    ui.tags.li(ui.HTML(
                        "<b>Priority 4:</b> Enhancing disaster preparedness for effective response, and to "
                        "<i>Build Back Better</i> in recovery, rehabilitation, and reconstruction."
                    )),
                ),

                ui.tags.hr(style="margin:20px 0; border-top:2px solid #ddd"),
                ui.output_ui("logos"),
            ),
        ),
    ),

    ui.tags.script("document.title = 'Risk-Related Projects';"),
    title="Mainland Coast Salish Area Risk-Related Projects Database",
)


# ---------- SERVER ----------
def server(input, output, session):

    MAP = Map(
        center=_points_centroid(ALL_POINTS)[:2],
        zoom=_points_centroid(ALL_POINTS)[2],
        layout=Layout(height="100%"),
        scroll_wheel_zoom=True,
        prefer_canvas=True,
    )
    MAP.add_control(ScaleControl(position="bottomleft"))
    base = TileLayer(url=OSM_URL, attribution=OSM_ATTR, name="OSM")
    MAP.add_layer(base)

    def _safe_input(callable_input, default):
        try:
            return callable_input()
        except Exception:
            return default

    layer_refs = {
        "base": base,
        "comm_rd": None,
        "comm_lg": None,
        "comm_fn": None,
        "highlight": None,
        "points_by_extent": {},
        "layer_present": {},
        "legend_control": None,
        "legend_checks": {},
        "legend_labels": {},
        "legend_checks_comm": {},
        "layers_control": None,
    }
    MAP._keepalive = layer_refs

    # ---- bounds reactive wiring ----
    def _get_bounds_now_noreactive():
        try:
            b = getattr(MAP, "bounds", None)
            if (
                isinstance(b,(list,tuple)) and len(b)==2 and
                isinstance(b[0],(list,tuple)) and len(b[0])==2 and
                isinstance(b[1],(list,tuple)) and len(b[1])==2
            ):
                s = float(b[0][0]); w = float(b[0][1])
                n = float(b[1][0]); e = float(b[1][1])
                if s <= n and w <= e:
                    return [[s,w],[n,e]]
        except Exception:
            pass
        return BOUNDS_DEFAULT

    b0 = _get_bounds_now_noreactive()
    bounds_state = reactive.Value(b0)
    prev_bounds = b0
    bounds_tick  = reactive.Value(0)

    def _on_map_change(change):
        nonlocal prev_bounds
        b = _get_bounds_now_noreactive()
        if b != prev_bounds:
            prev_bounds = b
            bounds_state.set(b)
            bounds_tick.set(bounds_tick.get() + 1)

    MAP.observe(_on_map_change, names=["bounds","center","zoom"])

    # ---------- UI small renders ----------
    @render.ui
    def ecos_how_filter():
        label = ECO_HOW_FIELD or "How Does the Project Outcome Aim to Provide Ecosystem Services?"
        if not ECO_HOW_FIELD:
            return ui.input_selectize("f_eco_how", label, choices=[], selected=[], multiple=True)
        raw_vals = {str((it.get("props") or {}).get(ECO_HOW_FIELD,"")).strip() for it in ALL_POINTS} - {""}
        return ui.input_selectize("f_eco_how", label, choices=sorted(raw_vals), selected=[], multiple=True)

    @render.ui
    def col_picker():
        excluded = set(FILTER_FIELDS) | HIDDEN_FIELDS
        if ECO_HOW_FIELD: excluded.add(ECO_HOW_FIELD)
        if ECO_YN_FIELD:  excluded.add(ECO_YN_FIELD)
        order2 = [k for k in KEY_ORDER if k not in excluded]
        default = [k for k in DEFAULT_SELECTED_FIELDS if k in order2]
        if not default:
            default = order2[:8] if order2 else []
        return ui.input_checkbox_group("cols", label="", choices=order2, selected=default, inline=False)

    # ---------- filtering ----------
    def _filter_points():
        q = (_safe_input(input.data_search, "") or "").strip().lower()
        selected_aims = set(_safe_input(input.f_aims, []) or [])
        selected_aim_fields = [AIM_FILTER_FIELDS[a] for a in selected_aims if a in AIM_FILTER_FIELDS]
        ecos_how_sel = set(_safe_input(input.f_eco_how, []) or [])

        pts = ALL_POINTS
        if q:
            pts = [
                it for it in pts
                if any((q in str(v).lower()) for v in (it.get("props") or {}).values())
            ]

        out = []
        for it in pts:
            props = it.get("props") or {}
            if selected_aim_fields:
                # Keep rows where at least one selected aim is marked Yes.
                if not any(str(props.get(col, "")).strip().upper() == "Y" for col in selected_aim_fields):
                    continue
            if ECO_HOW_FIELD and ecos_how_sel:
                v = str(props.get(ECO_HOW_FIELD,"")).strip()
                if v not in ecos_how_sel:
                    continue
            out.append(it)
        return out

    # display coords (snapped)
    def _disp_latlon(it):
        return ID2DISP_SNAP.get(it["id"], (it["lat"], it["lon"]))

    # community layers
    def _filter_fc_by_type_local(raw_gj, type_value):
        if not raw_gj or raw_gj.get("type") != "FeatureCollection":
            return {"type":"FeatureCollection","features":[]}
        feats = []
        for f in raw_gj.get("features", []):
            props = (f.get("properties") or {})
            if str(props.get(COMM_TYPE_FIELD,"")).strip().upper() == str(type_value).strip().upper():
                feats.append(f)
        return {"type":"FeatureCollection","features":feats}

    def _prep_boundaries_with_fallback_triple(raw_gj, exact, pad_deg, stride):
        if not raw_gj:
            empty = {"type":"FeatureCollection","features":[]}
            return empty, empty, empty

        raw_rd = _filter_fc_by_type_local(raw_gj, "RD")
        raw_lg = _filter_fc_by_type_local(raw_gj, "LG")
        raw_fn = _filter_fc_by_type_local(raw_gj, "FN")

        rd_lines, _ = _sanitize_bounds_to_lines(raw_rd, _points_bbox(ALL_POINTS), pad_deg, stride, exact=exact)
        lg_lines, _ = _sanitize_bounds_to_lines(raw_lg, _points_bbox(ALL_POINTS), pad_deg, stride, exact=exact)
        fn_lines, _ = _sanitize_bounds_to_lines(raw_fn, _points_bbox(ALL_POINTS), pad_deg, stride, exact=exact)

        if not (rd_lines and rd_lines.get("features")): rd_lines = raw_rd
        if not (lg_lines and lg_lines.get("features")): lg_lines = raw_lg
        if not (fn_lines and fn_lines.get("features")): fn_lines = raw_fn
        return rd_lines, lg_lines, fn_lines

    def _ensure_points_on_top():
        for k in EXTENT_ORDER:
            lyr = layer_refs["points_by_extent"].get(k)
            if lyr and layer_refs["layer_present"].get(k):
                try: MAP.remove_layer(lyr)
                except Exception: pass
                MAP.add_layer(lyr)
        if layer_refs.get("highlight"):
            try: MAP.remove_layer(layer_refs["highlight"])
            except Exception: pass
            MAP.add_layer(layer_refs["highlight"])

    def _ensure_community_layers():
        show = SHOW_COMMUNITY_DEFAULT
        raw  = RAW_COMMUNITY

        for key in ("comm_rd","comm_lg","comm_fn"):
            if not show and layer_refs.get(key):
                try: MAP.remove_layer(layer_refs[key])
                except Exception: pass
                layer_refs[key] = None

        if not show or not raw:
            _ensure_points_on_top()
            return

        rd_gj, lg_gj, fn_gj = _prep_boundaries_with_fallback_triple(
            raw, EXACT_BOUNDS_DEFAULT, CLIP_PAD_DEFAULT, STRIDE_DEFAULT
        )

        style_rd = {
            "color": COMM_LINE_COLORS["RD"], "weight": LINE_WIDTH_COMM_DEFAULT,
            "opacity": 0.7, "fill": False, "fillOpacity": 0.0
        }
        style_lg = {
            "color": COMM_LINE_COLORS["LG"], "weight": LINE_WIDTH_COMM_DEFAULT,
            "opacity": 0.9, "fill": False, "fillOpacity": 0.0
        }
        style_fn = {
            "color": COMM_LINE_COLORS["FN"], "weight": LINE_WIDTH_COMM_DEFAULT,
            "opacity": 1.0, "fill": False, "fillOpacity": 0.0
        }

        # RD
        if layer_refs.get("comm_rd") is None:
            lyr_rd = GeoJSON(data=rd_gj, style=style_rd, name="Community Boundaries — RD")
            MAP.add_layer(lyr_rd); layer_refs["comm_rd"] = lyr_rd
        else:
            layer_refs["comm_rd"].data = rd_gj
            try: layer_refs["comm_rd"].style = style_rd
            except Exception: pass

        # LG
        if layer_refs.get("comm_lg") is None:
            lyr_lg = GeoJSON(data=lg_gj, style=style_lg, name="Community Boundaries — LG")
            MAP.add_layer(lyr_lg); layer_refs["comm_lg"] = lyr_lg
        else:
            layer_refs["comm_lg"].data = lg_gj
            try: layer_refs["comm_lg"].style = style_lg
            except Exception: pass

        # FN
        if layer_refs.get("comm_fn") is None:
            lyr_fn = GeoJSON(data=fn_gj, style=style_fn, name="Community Boundaries — FN")
            MAP.add_layer(lyr_fn); layer_refs["comm_fn"] = lyr_fn
        else:
            layer_refs["comm_fn"].data = fn_gj
            try: layer_refs["comm_fn"].style = style_fn
            except Exception: pass

        _ensure_points_on_top()

    # extent buckets
    def _rows_by_extent(rows):
        buckets = {k: [] for k in EXTENT_ORDER}
        for it in rows:
            props = it.get("props") or {}
            key = _canon_extent(props.get(EXTENT_FIELD)) if EXTENT_FIELD else "Regional and broader"
            buckets[key].append(it)
        return buckets

    def _rows_to_fc(rows, canon_key):
        feats = []
        for it in rows:
            props = dict(it.get("props") or {})
            props["__extent_canon__"] = canon_key
            props["__base_lat__"] = it["lat"]
            props["__base_lon__"] = it["lon"]
            lat_disp, lon_disp = _disp_latlon(it)
            feats.append({
                "type":"Feature",
                "geometry":{"type":"Point","coordinates":[float(lon_disp), float(lat_disp)]},
                "properties":props,
            })
        return {"type":"FeatureCollection","features":feats}

    def _point_style_callback(feature, **kwargs):
        props = (feature or {}).get("properties") or {}
        canon = props.get("__extent_canon__")
        r = EXTENT_RADIUS.get(canon, 9)
        col = EXTENT_COLOR.get(canon, "#7c3aed")
        return {
            "color": col,
            "fillColor": col,
            "radius": r,
            "weight": 1,
            "opacity": 1.0,
            "fillOpacity": 0.7,
        }

    def _expand_bounds(b, frac=0.02, min_pad=0.005):
        (s,w),(n,e) = b
        pad_lat = max(min_pad, (n-s)*frac)
        pad_lon = max(min_pad, (e-w)*frac)
        return [[s-pad_lat,w-pad_lon],[n+pad_lat,e+pad_lon]]

    def _in_view_disp(it, b):
        bd = _expand_bounds(b)
        s,w = bd[0][0], bd[0][1]
        n,e = bd[1][0], bd[1][1]
        lat, lon = _disp_latlon(it)
        return (s <= lat <= n) and (w <= lon <= e)

    def _ensure_points_layers():
        for key in EXTENT_ORDER:
            if key not in layer_refs["points_by_extent"]:
                lyr = GeoJSON(
                    data=_rows_to_fc([], key),
                    name=f"Projects — {key}",
                    point_style={"color":"#1f6feb","fillColor":"#1f6feb","radius":6,
                                 "weight":1,"opacity":1.0,"fillOpacity":0.7},
                    style_callback=_point_style_callback,
                )
                try: lyr.on_click(_on_point_click_handler)
                except Exception: pass
                MAP.add_layer(lyr)
                layer_refs["points_by_extent"][key] = lyr
                layer_refs["layer_present"][key] = True

        if layer_refs.get("highlight") is None:
            def _hl_style(feature, **kwargs):
                props = (feature or {}).get("properties") or {}
                canon = props.get("__extent_canon__")
                col = EXTENT_COLOR.get(canon, "#000000")
                return {
                    "color": col,
                    "fillColor": col,
                    "radius": EXTENT_RADIUS.get(canon, 9) + 5,
                    "weight": 3,
                    "opacity": 0.9,
                    "fillOpacity": 0.0,
                }

            hl = GeoJSON(
                data={"type":"FeatureCollection","features":[]},
                name="Selection highlight",
                point_style={"color":"#000000","fillColor":"#000000","radius":12,
                             "weight":3,"opacity":0.9,"fillOpacity":0.0},
                style_callback=_hl_style,
            )
            MAP.add_layer(hl)
            layer_refs["highlight"] = hl

    def _update_legend_counts_only(rows=None, buckets=None, b=None):
        if rows is None: rows = _filter_points()
        if b is None:    b = _get_bounds_now_noreactive()
        if not rows:
            for key in EXTENT_ORDER:
                lbl = layer_refs["legend_labels"].get(key)
                if lbl:
                    color = EXTENT_COLOR[key]
                    lbl.value = (
                        "<div style='display:flex;align-items:center;gap:8px;'>"
                        f"<span style='display:inline-block;width:14px;height:14px;background:{color};"
                        "border-radius:3px;border:1px solid #1112;'></span>"
                        f"<span style='font-size:12px;color:#111'>{html.escape(key)} (0)</span>"
                        "</div>"
                    )
            return

        if buckets is None: buckets = _rows_by_extent(rows)
        for key in EXTENT_ORDER:
            lbl = layer_refs["legend_labels"].get(key)
            if not lbl: continue
            color = EXTENT_COLOR[key]
            count = sum(1 for it in buckets.get(key, []) if _in_view_disp(it, b))
            lbl.value = (
                "<div style='display:flex;align-items:center;gap:8px;'>"
                f"<span style='display:inline-block;width:14px;height:14px;background:{color};"
                "border-radius:3px;border:1px solid #1112;'></span>"
                f"<span style='font-size:12px;color:#111'>{html.escape(key)} ({count})</span>"
                "</div>"
            )

    def _refresh_points_and_counts():
        rows = _filter_points()
        buckets = _rows_by_extent(rows)
        for key, lyr in layer_refs["points_by_extent"].items():
            lyr.data = _rows_to_fc(buckets.get(key, []), key)
        _update_legend_counts_only(rows, buckets)
        _ensure_points_on_top()

    # clicks
    clicked_rows = reactive.Value([])
    OVERLAP_M_THRESHOLD = 2.0

    def _rows_overlapping_disp(lat_d, lon_d, pool_rows):
        out = []
        for it in pool_rows:
            props = it.get("props") or {}
            canon = _canon_extent(props.get(EXTENT_FIELD)) if EXTENT_FIELD else "Regional and broader"
            if not layer_refs["layer_present"].get(canon, True):
                continue
            lat_s, lon_s = _disp_latlon(it)
            if _haversine_m(lat_d, lon_d, lat_s, lon_s) <= OVERLAP_M_THRESHOLD:
                out.append(it)
        return out

    def _on_point_click_handler(**kwargs):
        feat = (kwargs or {}).get("feature") or {}
        geom = feat.get("geometry") or {}
        coords = geom.get("coordinates") or []
        if not (isinstance(coords,(list,tuple)) and len(coords)>=2):
            clicked_rows.set([])
            if layer_refs.get("highlight"):
                layer_refs["highlight"].data = {"type":"FeatureCollection","features":[]}
            return
        lon_d, lat_d = float(coords[0]), float(coords[1])
        filtered = _filter_points()
        group = _rows_overlapping_disp(lat_d, lon_d, filtered)
        clicked_rows.set(group)

        if layer_refs.get("highlight"):
            feats = []
            for it in group:
                canon = _canon_extent((it.get("props") or {}).get(EXTENT_FIELD))
                lat_s, lon_s = _disp_latlon(it)
                feats.append({
                    "type":"Feature",
                    "geometry":{"type":"Point","coordinates":[float(lon_s), float(lat_s)]},
                    "properties":{"__extent_canon__": canon},
                })
            layer_refs["highlight"].data = {"type":"FeatureCollection","features":feats}
            _ensure_points_on_top()

    # legend
    def _create_legend_control_once():
        if layer_refs.get("legend_control") is not None:
            wc = layer_refs["legend_control"]
            try:
                if getattr(wc, "parent", None) is None:
                    MAP.add_control(wc)
            except Exception:
                pass
            return

        rows = []
        rows.append(HTML("<div style='font-weight:600;margin:0 0 1px 0'>Legend</div>"))
        rows.append(HTML("<div style='font-size:12px;color:#111;margin:0px 0 1px 0;opacity:.9'>Projects with different extents</div>"))

        for key in EXTENT_ORDER:
            color = EXTENT_COLOR[key]
            cb = Checkbox(description="", indent=False, value=True, layout=Layout(width="20px", height="18px"))
            layer_refs["legend_checks"][key] = cb
            lbl = HTML(
                "<div style='display:flex;align-items:center;gap:8px;'>"
                f"<span style='display:inline-block;width:14px;height:14px;background:{color};"
                "border-radius:3px;border:1px solid #1112;'></span>"
                f"<span style='font-size:12px;color:#111'>{html.escape(key)} (0)</span>"
                "</div>"
            )
            layer_refs["legend_labels"][key] = lbl
            rows.append(HBox([cb, lbl], layout=Layout(align_items="center")))

        rows.append(HTML("<div style='font-size:12px;color:#111;margin:2px 0 1px 0;opacity:.9'>Community boundaries</div>"))

        for label_txt, key in [("Regional districts","RD"), ("Local governments","LG"), ("First Nations","FN")]:
            color = COMM_LINE_COLORS[key]
            cb = Checkbox(description="", indent=False, value=True, layout=Layout(width="20px", height="18px"))
            layer_refs["legend_checks_comm"][key] = cb
            item = HBox([
                cb,
                HTML(
                    "<div style='display:flex;align-items:center;gap:8px;'>"
                    f"<span style='display:inline-block;width:22px;height:0;border-top:3px solid {color};'></span>"
                    f"<span style='font-size:12px;color:#111'>{label_txt}</span>"
                    "</div>"
                )
            ], layout=Layout(align_items="center"))
            rows.append(item)

        container = VBox(
            rows,
            layout=Layout(
                padding="6px 8px",
                width="280px",
                background="white",
                border="1px solid rgba(0,0,0,0.15)",
                border_radius="8px",
                overflow="visible",
                max_height=None,
                height="auto",
            ),
        )

        wc = WidgetControl(widget=container, position="topright")
        MAP.add_control(wc)
        layer_refs["legend_control"] = wc

        # Extent bucket toggles
        for key, cb in layer_refs["legend_checks"].items():
            def _handler(change, k=key):
                if change["name"] != "value":
                    return
                lyr = layer_refs["points_by_extent"].get(k)
                if not lyr:
                    return
                if change["new"]:
                    if not layer_refs["layer_present"].get(k):
                        MAP.add_layer(lyr)
                        layer_refs["layer_present"][k] = True
                        _ensure_points_on_top()
                else:
                    if layer_refs["layer_present"].get(k):
                        try: MAP.remove_layer(lyr)
                        except Exception: pass
                        layer_refs["layer_present"][k] = False
            cb.observe(_handler)

        # Community boundary toggles
        def _toggle_comm_layer(which_key, on):
            lyr_key = {"RD":"comm_rd","LG":"comm_lg","FN":"comm_fn"}[which_key]
            lyr = layer_refs.get(lyr_key)
            if not lyr:
                return
            if on:
                try: MAP.remove_layer(lyr)
                except Exception: pass
                MAP.add_layer(lyr)
            else:
                try: MAP.remove_layer(lyr)
                except Exception: pass
            _ensure_points_on_top()

        for k, cb in layer_refs["legend_checks_comm"].items():
            def _handler(change, kk=k):
                if change["name"] != "value":
                    return
                _toggle_comm_layer(kk, bool(change["new"]))
            cb.observe(_handler)

    # initial build
    def _initial_build():
        _create_legend_control_once()
        _ensure_points_layers()
        _refresh_points_and_counts()
        if RAW_COMMUNITY:
            _ensure_community_layers()
        if layer_refs.get("layers_control") is None:
            lc = LayersControl(position="topleft")
            MAP.add_control(lc)
            layer_refs["layers_control"] = lc
        _ensure_points_on_top()

    _initial_build()

    @reactive.effect
    def _eff_comm():
        _ensure_community_layers()

    @reactive.effect
    def _eff_points():
        _ensure_points_layers()
        _refresh_points_and_counts()

    @reactive.effect
    def _eff_bounds_counts():
        _ = bounds_state.get()
        _update_legend_counts_only()

    @render_widget
    def m():
        _create_legend_control_once()
        return MAP

    # prefer Project Name/Title first
    def _move_project_name_first(cols):
        for k in cols:
            s = k.strip().lower()
            if "project" in s and ("name" in s or "title" in s):
                return [k] + [c for c in cols if c != k]
        return cols

    # HTML table helper (sticky)
    def _html_table(rows, cols, max_vh="72vh"):
        if not rows:
            return "<div style='opacity:.7'>No rows</div>"
        thead = "".join(
            f"<th style='text-align:left;padding:6px 10px 6px 8px;white-space:nowrap'>{html.escape(str(k))}</th>"
            for k in cols
        )
        body = []
        for it in rows:
            props = it.get("props") or {}
            tds = "".join(
                f"<td style='padding:6px 10px 6px 8px;vertical-align:top'>{html.escape(str(props.get(k,'')))}</td>"
                for k in cols
            )
            body.append(f"<tr>{tds}</tr>")
        table = (
            "<table class='sticky' style='font-size:14px;width:100%'>"
            f"<thead><tr>{thead}</tr></thead><tbody>{''.join(body)}</tbody></table>"
        )
        return f"<div class='sticky-wrap' style='max-height:{max_vh};'>{table}</div>"

    @render.ui
    def table_data():
        rows = _filter_points()
        excluded = set(FILTER_FIELDS) | HIDDEN_FIELDS
        if ECO_HOW_FIELD: excluded.add(ECO_HOW_FIELD)
        if ECO_YN_FIELD:  excluded.add(ECO_YN_FIELD)
        order2 = [k for k in KEY_ORDER if k not in excluded]
        cols = [c for c in (input.cols() or []) if c in set(order2)]
        cols = _move_project_name_first(cols)
        if not cols:
            return ui.HTML("<div style='opacity:.7'>Choose at least one column in the sidebar.</div>")
        slim = [{"props": {k: (it.get("props") or {}).get(k, "") for k in cols}} for it in rows[:2000]]
        return ui.HTML(_html_table(slim, cols))

    @render.ui
    def clicked_table():
        rows = clicked_rows.get() or []
        if not rows:
            return ui.HTML("<div style='opacity:.6'>Click a project point to list details here.</div>")
        excluded = set(FILTER_FIELDS) | HIDDEN_FIELDS
        if ECO_HOW_FIELD: excluded.add(ECO_HOW_FIELD)
        if ECO_YN_FIELD:  excluded.add(ECO_YN_FIELD)
        order2 = [k for k in KEY_ORDER if k not in excluded]
        cols = [c for c in (input.cols() or []) if c in set(order2)]
        cols = _move_project_name_first(cols)
        if not cols:
            return ui.HTML("<div style='opacity:.6'>Choose columns in the sidebar to show fields here.</div>")
        slim = [{"props": {k: (it.get("props") or {}).get(k, "") for k in cols}} for it in rows[:400]]
        return ui.HTML(_html_table(slim, cols, max_vh="28vh"))

    @render.ui
    def readme_table():
        rows = deliverables_rows()
        cols = ["Deliverable", "Function", "Intended Purpose", "Intended Users"]
        return ui.HTML(html_table_from_rows(rows, cols))

    @render.ui
    def logos():
        logos_data = logo_files_to_data_uris()
        if not logos_data:
            return ui.HTML(
                "<div style='opacity:.7'>No logos found. Put images in <code>./www/logos/</code> "
                "(png/jpg/jpeg/svg/webp). Example: <code>www/logos/logo1.png</code></div>"
            )
        blocks = []
        for item in logos_data:
            blocks.append(
                ui.div(
                    {"style":"display:flex; flex-direction:column; align-items:center; width:200px"},
                    ui.tags.img(
                        src=item["data_uri"],
                        alt=item["name"],
                        style=(
                            "height:60px; max-width:180px; object-fit:contain; background:#fff; "
                            "padding:4px; border-radius:6px; box-shadow:0 0 0 1px rgba(0,0,0,0.05)"
                        ),
                    ),
                )
            )
        return ui.div({"style":"display:flex; gap:24px; align-items:flex-start; flex-wrap:wrap;"}, *blocks)

app = App(app_ui, server)
