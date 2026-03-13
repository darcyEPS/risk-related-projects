"""Server logic for the Shiny app."""

import html
from ipyleaflet import Map, TileLayer, ScaleControl, GeoJSON, LayersControl, WidgetControl
from ipywidgets import Layout, VBox, HBox, HTML, Checkbox
from shiny import render, reactive
from shinywidgets import render_widget

from config import (
    OSM_URL,
    OSM_ATTR,
    EXTENT_ORDER,
    EXTENT_COLOR,
    EXTENT_RADIUS,
    COMM_TYPE_FIELD,
    COMM_LINE_COLORS,
    AIM_FILTER_FIELDS,
    FILTER_FIELDS,
    SHOW_COMMUNITY_DEFAULT,
    EXACT_BOUNDS_DEFAULT,
    LINE_WIDTH_COMM_DEFAULT,
    CLIP_PAD_DEFAULT,
    STRIDE_DEFAULT,
    DEFAULT_SELECTED_FIELDS,
)
from data import (
    ALL_POINTS,
    KEY_ORDER,
    PTS_BBOX,
    RAW_COMMUNITY,
    BOUNDS_DEFAULT,
    ID2DISP_SNAP,
    EXTENT_FIELD,
    ECO_YN_FIELD,
    ECO_HOW_FIELD,
    HIDDEN_FIELDS,
)
from helpers import (
    _points_centroid,
    _canon_extent,
    _haversine_m,
    _rows_to_fc,
    _disp_latlon,
    _points_bbox,
    _sanitize_bounds_to_lines,
    load_information_markdown,
    logo_files_to_data_uris,
    load_logos_urls,
)


def server(input, output, session):
    """Main server function for Shiny app."""

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
        """Safely get input value."""
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
        """Get current map bounds."""
        try:
            b = getattr(MAP, "bounds", None)
            if (
                isinstance(b, (list, tuple))
                and len(b) == 2
                and isinstance(b[0], (list, tuple))
                and len(b[0]) == 2
                and isinstance(b[1], (list, tuple))
                and len(b[1]) == 2
            ):
                s = float(b[0][0])
                w = float(b[0][1])
                n = float(b[1][0])
                e = float(b[1][1])
                if s <= n and w <= e:
                    return [[s, w], [n, e]]
        except Exception:
            pass
        return BOUNDS_DEFAULT

    b0 = _get_bounds_now_noreactive()
    bounds_state = reactive.Value(b0)
    prev_bounds = b0
    bounds_tick = reactive.Value(0)

    def _on_map_change(change):
        nonlocal prev_bounds
        b = _get_bounds_now_noreactive()
        if b != prev_bounds:
            prev_bounds = b
            bounds_state.set(b)
            bounds_tick.set(bounds_tick.get() + 1)

    MAP.observe(_on_map_change, names=["bounds", "center", "zoom"])

    # ---------- UI small renders ----------
    @render.ui
    def ecos_how_filter():
        """Render ecosystem services filter."""
        label = ECO_HOW_FIELD or "How Does the Project Outcome Aim to Provide Ecosystem Services?"
        if not ECO_HOW_FIELD:
            from shiny import ui

            selectize_input = ui.input_selectize("f_eco_how", "", choices=[], selected=[], multiple=True)
        else:
            from shiny import ui

            raw_vals = {
                str((it.get("props") or {}).get(ECO_HOW_FIELD, "")).strip() for it in ALL_POINTS
            } - {""}
            selectize_input = ui.input_selectize(
                "f_eco_how", "", choices=sorted(raw_vals), selected=[], multiple=True
            )

        from shiny import ui

        return ui.div(
            {"class": "filter-section"},
            ui.div(
                {"class": "filter-section-header"},
                ui.div(
                    "Ecosystem Services",
                    style="display:flex; align-items:center; gap:6px; font-weight:600; color:#1e293b; font-size:14px; text-transform:uppercase; letter-spacing:0.5px; opacity:0.9;",
                ),
            ),
            selectize_input,
        )

    @render.ui
    def col_picker():
        """Render column picker."""
        from shiny import ui

        excluded = set(FILTER_FIELDS) | HIDDEN_FIELDS
        if ECO_HOW_FIELD:
            excluded.add(ECO_HOW_FIELD)
        if ECO_YN_FIELD:
            excluded.add(ECO_YN_FIELD)
        order2 = [k for k in KEY_ORDER if k not in excluded]
        default = [k for k in DEFAULT_SELECTED_FIELDS if k in order2]
        if not default:
            default = order2[:8] if order2 else []
        return ui.input_checkbox_group("cols", label="", choices=order2, selected=default, inline=False)

    # ---------- filtering ----------
    def _filter_points():
        """Apply all filters to points."""
        q = (_safe_input(input.data_search, "") or "").strip().lower()
        selected_aims = set(_safe_input(input.f_aims, []) or [])
        selected_aim_fields = [AIM_FILTER_FIELDS[a] for a in selected_aims if a in AIM_FILTER_FIELDS]
        ecos_how_sel = set(_safe_input(input.f_eco_how, []) or [])

        pts = ALL_POINTS
        if q:
            pts = [
                it
                for it in pts
                if any((q in str(v).lower()) for v in (it.get("props") or {}).values())
            ]

        out = []
        for it in pts:
            props = it.get("props") or {}
            if selected_aim_fields:
                if not any(
                    str(props.get(col, "")).strip().upper() == "Y" for col in selected_aim_fields
                ):
                    continue
            if ECO_HOW_FIELD and ecos_how_sel:
                v = str(props.get(ECO_HOW_FIELD, "")).strip()
                if v not in ecos_how_sel:
                    continue
            out.append(it)
        return out

    # community layers
    def _filter_fc_by_type_local(raw_gj, type_value):
        """Filter GeoJSON by type field."""
        if not raw_gj or raw_gj.get("type") != "FeatureCollection":
            return {"type": "FeatureCollection", "features": []}
        feats = []
        for f in raw_gj.get("features", []):
            props = f.get("properties") or {}
            if str(props.get(COMM_TYPE_FIELD, "")).strip().upper() == str(type_value).strip().upper():
                feats.append(f)
        return {"type": "FeatureCollection", "features": feats}

    def _prep_boundaries_with_fallback_triple(raw_gj, exact, pad_deg, stride):
        """Prepare boundary layers (RD, LG, FN)."""
        if not raw_gj:
            empty = {"type": "FeatureCollection", "features": []}
            return empty, empty, empty

        raw_rd = _filter_fc_by_type_local(raw_gj, "RD")
        raw_lg = _filter_fc_by_type_local(raw_gj, "LG")
        raw_fn = _filter_fc_by_type_local(raw_gj, "FN")

        rd_lines, _ = _sanitize_bounds_to_lines(
            raw_rd, _points_bbox(ALL_POINTS), pad_deg, stride, exact=exact
        )
        lg_lines, _ = _sanitize_bounds_to_lines(
            raw_lg, _points_bbox(ALL_POINTS), pad_deg, stride, exact=exact
        )
        fn_lines, _ = _sanitize_bounds_to_lines(
            raw_fn, _points_bbox(ALL_POINTS), pad_deg, stride, exact=exact
        )

        if not (rd_lines and rd_lines.get("features")):
            rd_lines = raw_rd
        if not (lg_lines and lg_lines.get("features")):
            lg_lines = raw_lg
        if not (fn_lines and fn_lines.get("features")):
            fn_lines = raw_fn
        return rd_lines, lg_lines, fn_lines

    def _ensure_points_on_top():
        """Re-order layers so points appear on top."""
        for k in EXTENT_ORDER:
            lyr = layer_refs["points_by_extent"].get(k)
            if lyr and layer_refs["layer_present"].get(k):
                try:
                    MAP.remove_layer(lyr)
                except Exception:
                    pass
                MAP.add_layer(lyr)
        if layer_refs.get("highlight"):
            try:
                MAP.remove_layer(layer_refs["highlight"])
            except Exception:
                pass
            MAP.add_layer(layer_refs["highlight"])

    def _ensure_community_layers():
        """Ensure community boundary layers are present/updated."""
        show = SHOW_COMMUNITY_DEFAULT
        raw = RAW_COMMUNITY

        for key in ("comm_rd", "comm_lg", "comm_fn"):
            if not show and layer_refs.get(key):
                try:
                    MAP.remove_layer(layer_refs[key])
                except Exception:
                    pass
                layer_refs[key] = None

        if not show or not raw:
            _ensure_points_on_top()
            return

        rd_gj, lg_gj, fn_gj = _prep_boundaries_with_fallback_triple(
            raw, EXACT_BOUNDS_DEFAULT, CLIP_PAD_DEFAULT, STRIDE_DEFAULT
        )

        style_rd = {
            "color": COMM_LINE_COLORS["RD"],
            "weight": LINE_WIDTH_COMM_DEFAULT,
            "opacity": 0.7,
            "fill": False,
            "fillOpacity": 0.0,
        }
        style_lg = {
            "color": COMM_LINE_COLORS["LG"],
            "weight": LINE_WIDTH_COMM_DEFAULT,
            "opacity": 0.9,
            "fill": False,
            "fillOpacity": 0.0,
        }
        style_fn = {
            "color": COMM_LINE_COLORS["FN"],
            "weight": LINE_WIDTH_COMM_DEFAULT,
            "opacity": 1.0,
            "fill": False,
            "fillOpacity": 0.0,
        }

        # RD
        if layer_refs.get("comm_rd") is None:
            lyr_rd = GeoJSON(data=rd_gj, style=style_rd, name="Community Boundaries — RD")
            MAP.add_layer(lyr_rd)
            layer_refs["comm_rd"] = lyr_rd
        else:
            layer_refs["comm_rd"].data = rd_gj
            try:
                layer_refs["comm_rd"].style = style_rd
            except Exception:
                pass

        # LG
        if layer_refs.get("comm_lg") is None:
            lyr_lg = GeoJSON(data=lg_gj, style=style_lg, name="Community Boundaries — LG")
            MAP.add_layer(lyr_lg)
            layer_refs["comm_lg"] = lyr_lg
        else:
            layer_refs["comm_lg"].data = lg_gj
            try:
                layer_refs["comm_lg"].style = style_lg
            except Exception:
                pass

        # FN
        if layer_refs.get("comm_fn") is None:
            lyr_fn = GeoJSON(data=fn_gj, style=style_fn, name="Community Boundaries — FN")
            MAP.add_layer(lyr_fn)
            layer_refs["comm_fn"] = lyr_fn
        else:
            layer_refs["comm_fn"].data = fn_gj
            try:
                layer_refs["comm_fn"].style = style_fn
            except Exception:
                pass

        _ensure_points_on_top()

    # extent buckets
    def _rows_by_extent(rows):
        """Group rows by extent bucket."""
        buckets = {k: [] for k in EXTENT_ORDER}
        for it in rows:
            props = it.get("props") or {}
            key = _canon_extent(props.get(EXTENT_FIELD)) if EXTENT_FIELD else "Regional and broader"
            buckets[key].append(it)
        return buckets

    def _point_style_callback(feature, **kwargs):
        """Style callback for point features."""
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
        """Expand bounds by a fraction."""
        (s, w), (n, e) = b
        pad_lat = max(min_pad, (n - s) * frac)
        pad_lon = max(min_pad, (e - w) * frac)
        return [[s - pad_lat, w - pad_lon], [n + pad_lat, e + pad_lon]]

    def _in_view_disp(it, b):
        """Check if displayed point is within bounds."""
        bd = _expand_bounds(b)
        s, w = bd[0][0], bd[0][1]
        n, e = bd[1][0], bd[1][1]
        lat, lon = _disp_latlon(it, ID2DISP_SNAP)
        return (s <= lat <= n) and (w <= lon <= e)

    def _ensure_points_layers():
        """Ensure point layers exist for each extent bucket."""
        for key in EXTENT_ORDER:
            if key not in layer_refs["points_by_extent"]:
                lyr = GeoJSON(
                    data=_rows_to_fc([], key, ID2DISP_SNAP),
                    name=f"Projects — {key}",
                    point_style={
                        "color": "#1f6feb",
                        "fillColor": "#1f6feb",
                        "radius": 6,
                        "weight": 1,
                        "opacity": 1.0,
                        "fillOpacity": 0.7,
                    },
                    style_callback=_point_style_callback,
                )
                try:
                    lyr.on_click(_on_point_click_handler)
                except Exception:
                    pass
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
                data={"type": "FeatureCollection", "features": []},
                name="Selection highlight",
                point_style={
                    "color": "#000000",
                    "fillColor": "#000000",
                    "radius": 12,
                    "weight": 3,
                    "opacity": 0.9,
                    "fillOpacity": 0.0,
                },
                style_callback=_hl_style,
            )
            MAP.add_layer(hl)
            layer_refs["highlight"] = hl

    def _update_legend_counts_only(rows=None, buckets=None, b=None):
        """Update legend counts without re-rendering."""
        if rows is None:
            rows = _filter_points()
        if b is None:
            b = _get_bounds_now_noreactive()
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

        if buckets is None:
            buckets = _rows_by_extent(rows)
        for key in EXTENT_ORDER:
            lbl = layer_refs["legend_labels"].get(key)
            if not lbl:
                continue
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
        """Refresh point layers and counts."""
        rows = _filter_points()
        buckets = _rows_by_extent(rows)
        for key, lyr in layer_refs["points_by_extent"].items():
            lyr.data = _rows_to_fc(buckets.get(key, []), key, ID2DISP_SNAP)
        _update_legend_counts_only(rows, buckets)
        _ensure_points_on_top()

    # clicks
    clicked_rows = reactive.Value([])
    OVERLAP_M_THRESHOLD = 2.0

    def _rows_overlapping_disp(lat_d, lon_d, pool_rows):
        """Get rows with displayed coords within threshold."""
        out = []
        for it in pool_rows:
            props = it.get("props") or {}
            canon = _canon_extent(props.get(EXTENT_FIELD)) if EXTENT_FIELD else "Regional and broader"
            if not layer_refs["layer_present"].get(canon, True):
                continue
            lat_s, lon_s = _disp_latlon(it, ID2DISP_SNAP)
            if _haversine_m(lat_d, lon_d, lat_s, lon_s) <= OVERLAP_M_THRESHOLD:
                out.append(it)
        return out

    def _on_point_click_handler(**kwargs):
        """Handle point click events."""
        feat = (kwargs or {}).get("feature") or {}
        geom = feat.get("geometry") or {}
        coords = geom.get("coordinates") or []
        if not (isinstance(coords, (list, tuple)) and len(coords) >= 2):
            clicked_rows.set([])
            if layer_refs.get("highlight"):
                layer_refs["highlight"].data = {"type": "FeatureCollection", "features": []}
            return
        lon_d, lat_d = float(coords[0]), float(coords[1])
        filtered = _filter_points()
        group = _rows_overlapping_disp(lat_d, lon_d, filtered)
        clicked_rows.set(group)

        if layer_refs.get("highlight"):
            feats = []
            for it in group:
                canon = _canon_extent((it.get("props") or {}).get(EXTENT_FIELD))
                lat_s, lon_s = _disp_latlon(it, ID2DISP_SNAP)
                feats.append(
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [float(lon_s), float(lat_s)]},
                        "properties": {"__extent_canon__": canon},
                    }
                )
            layer_refs["highlight"].data = {"type": "FeatureCollection", "features": feats}
            _ensure_points_on_top()

    # legend
    def _create_legend_control_once():
        """Create legend control (once only)."""
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
        rows.append(
            HTML(
                "<div style='font-size:12px;color:#111;margin:0px 0 1px 0;opacity:.9'>Projects with different extents</div>"
            )
        )

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

        rows.append(
            HTML(
                "<div style='font-size:12px;color:#111;margin:2px 0 1px 0;opacity:.9'>Community boundaries</div>"
            )
        )

        for label_txt, key in [("Regional districts", "RD"), ("Local governments", "LG"), ("First Nations", "FN")]:
            color = COMM_LINE_COLORS[key]
            cb = Checkbox(description="", indent=False, value=True, layout=Layout(width="20px", height="18px"))
            layer_refs["legend_checks_comm"][key] = cb
            item = HBox(
                [
                    cb,
                    HTML(
                        "<div style='display:flex;align-items:center;gap:8px;'>"
                        f"<span style='display:inline-block;width:22px;height:0;border-top:3px solid {color};'></span>"
                        f"<span style='font-size:12px;color:#111'>{label_txt}</span>"
                        "</div>"
                    ),
                ],
                layout=Layout(align_items="center"),
            )
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
                        try:
                            MAP.remove_layer(lyr)
                        except Exception:
                            pass
                        layer_refs["layer_present"][k] = False

            cb.observe(_handler)

        # Community boundary toggles
        def _toggle_comm_layer(which_key, on):
            lyr_key = {"RD": "comm_rd", "LG": "comm_lg", "FN": "comm_fn"}[which_key]
            lyr = layer_refs.get(lyr_key)
            if not lyr:
                return
            if on:
                try:
                    MAP.remove_layer(lyr)
                except Exception:
                    pass
                MAP.add_layer(lyr)
            else:
                try:
                    MAP.remove_layer(lyr)
                except Exception:
                    pass
            _ensure_points_on_top()

        for k, cb in layer_refs["legend_checks_comm"].items():

            def _handler(change, kk=k):
                if change["name"] != "value":
                    return
                _toggle_comm_layer(kk, bool(change["new"]))

            cb.observe(_handler)

    # initial build
    def _initial_build():
        """Initial setup of map and layers."""
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
        """Reactive effect for community layers."""
        _ensure_community_layers()

    @reactive.effect
    def _eff_points():
        """Reactive effect for point layers."""
        _ensure_points_layers()
        _refresh_points_and_counts()

    @reactive.effect
    def _eff_bounds_counts():
        """Reactive effect for bounds and counts."""
        _ = bounds_state.get()
        _update_legend_counts_only()

    @render_widget
    def m():
        """Render the map widget."""
        _create_legend_control_once()
        return MAP

    # prefer Project Name/Title first
    def _move_project_name_first(cols):
        """Reorder columns to show project name first."""
        for k in cols:
            s = k.strip().lower()
            if "project" in s and ("name" in s or "title" in s):
                return [k] + [c for c in cols if c != k]
        return cols

    # HTML table helper (sticky)
    def _html_table(rows, cols, max_vh=None):
        """Generate HTML table."""
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
                f"<td style='padding:6px 10px 6px 8px;vertical-align:top'>{html.escape(str(props.get(k, '')))}</td>"
                for k in cols
            )
            body.append(f"<tr>{tds}</tr>")
        table = (
            "<table class='sticky' style='font-size:14px;width:100%'>"
            f"<thead><tr>{thead}</tr></thead><tbody>{''.join(body)}</tbody></table>"
        )
        style = "width:100%;"
        if max_vh:
            style += f" max-height:{max_vh}; overflow:auto;"
        return f"<div class='sticky-wrap' style='{style}'>{table}</div>"

    @render.ui
    def table_data():
        """Render data table."""
        from shiny import ui

        rows = _filter_points()
        excluded = set(FILTER_FIELDS) | HIDDEN_FIELDS
        if ECO_HOW_FIELD:
            excluded.add(ECO_HOW_FIELD)
        if ECO_YN_FIELD:
            excluded.add(ECO_YN_FIELD)
        order2 = [k for k in KEY_ORDER if k not in excluded]
        cols = [c for c in (input.cols() or []) if c in set(order2)]
        cols = _move_project_name_first(cols)
        if not cols:
            return ui.HTML("<div style='opacity:.7'>Choose at least one column in the sidebar.</div>")
        slim = [{"props": {k: (it.get("props") or {}).get(k, "") for k in cols}} for it in rows[:2000]]
        return ui.HTML(_html_table(slim, cols))

    @render.ui
    def clicked_table():
        """Render clicked project table."""
        from shiny import ui

        rows = clicked_rows.get() or []
        if not rows:
            return ui.HTML("<div style='opacity:.6'>Click a project point to list details here.</div>")
        excluded = set(FILTER_FIELDS) | HIDDEN_FIELDS
        if ECO_HOW_FIELD:
            excluded.add(ECO_HOW_FIELD)
        if ECO_YN_FIELD:
            excluded.add(ECO_YN_FIELD)
        order2 = [k for k in KEY_ORDER if k not in excluded]
        cols = [c for c in (input.cols() or []) if c in set(order2)]
        cols = _move_project_name_first(cols)
        if not cols:
            return ui.HTML("<div style='opacity:.6'>Choose columns in the sidebar to show fields here.</div>")
        slim = [{"props": {k: (it.get("props") or {}).get(k, "") for k in cols}} for it in rows[:400]]
        return ui.HTML(_html_table(slim, cols))

    @render.ui
    def logos():
        """Render logos."""
        from shiny import ui

        logos_data = logo_files_to_data_uris()
        if not logos_data:
            return ui.HTML(
                "<div style='opacity:.7'>No logos found. Put images in <code>./graphics/logos/</code> "
                "(png/jpg/jpeg/svg/webp). Example: <code>graphics/logos/logo1.png</code></div>"
            )
        logos_urls = load_logos_urls()
        blocks = []
        for item in logos_data:
            url = logos_urls.get(item["name"])
            img_elem = ui.tags.img(
                src=item["data_uri"],
                alt=item["name"],
                style=(
                    "height:85px; max-width:160px; object-fit:contain; background:#fff; "
                    "padding:4px; border-radius:6px; box-shadow:0 0 0 1px rgba(0,0,0,0.05); cursor:pointer; "
                    "transition:transform 0.2s, box-shadow 0.2s;"
                ),
            )

            if url and url.startswith("http"):
                elem = ui.tags.a(
                    img_elem,
                    href=url,
                    target="_blank",
                    rel="noopener noreferrer",
                    style="text-decoration:none; display:flex; flex-direction:column; align-items:center; justify-content:center;",
                )
            else:
                elem = ui.div(
                    {"style": "display:flex; flex-direction:column; align-items:center; justify-content:center;"},
                    img_elem,
                )

            blocks.append(elem)
        return ui.div({"style": "display:flex; gap:24px; align-items:flex-start;"}, *blocks)

    @render.ui
    def information_content():
        """Render information content."""
        from shiny import ui

        html_content = load_information_markdown()
        return ui.HTML(html_content)
