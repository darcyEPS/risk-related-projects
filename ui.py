"""UI components and layout."""

from shiny import ui
from shinywidgets import output_widget

from config import AIM_FILTER_CHOICES, DEFAULT_SELECTED_FIELDS

# Build the main UI
app_ui = ui.page_sidebar(
    # Sidebar
    ui.sidebar(
        # Header
        ui.div(
            ui.div(
                {"style": "display:flex; align-items:center; gap:8px; margin-bottom:0px;"},
                ui.div("Filters", style="font-size:20px; font-weight:700; color:#1e293b; letter-spacing:-0.5px;"),
            ),
        ),
        # Filter Sections Container
        ui.div(
            {"class": "filter-sections"},
            # 1. Study Outcome Aims Section
            ui.div(
                {"class": "filter-section"},
                ui.div(
                    {"class": "filter-section-header"},
                    ui.div(
                        "Study Outcome Aims",
                        style="display:flex; align-items:center; gap:6px; font-weight:600; color:#1e293b; margin-bottom:10px; font-size:14px; text-transform:uppercase; letter-spacing:0.5px; opacity:0.9; font-family:'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;",
                    ),
                ),
                ui.input_checkbox_group(
                    "f_aims",
                    "",
                    choices=AIM_FILTER_CHOICES,
                    selected=[],
                    inline=False,
                ),
            ),
            # 2. Ecosystem Services Section
            ui.output_ui("ecos_how_filter"),
            # Divider
            ui.div({"style": "height:1px; background:linear-gradient(to right, #cbd5e1, #e2e8f0, #cbd5e1); margin:12px 0;"}),
            # 3. Data Display Section
            ui.div(
                {"class": "filter-section"},
                ui.div(
                    {"class": "filter-section-header"},
                    ui.div(
                        "Fields to Display",
                        style="display:flex; align-items:center; gap:6px; font-weight:600; color:#1e293b; margin-bottom:10px; font-size:14px; text-transform:uppercase; letter-spacing:0.5px; opacity:0.9; font-family:'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;",
                    ),
                    style="margin-bottom:4px;",
                ),
                # ui.div(
                #     {"style": "font-size:12px; color:#64748b; margin-bottom:10px; line-height:1.4;"},
                #     "Select columns to display in the data table.",
                # ),
                ui.output_ui("col_picker"),
            ),
            style="display:flex; flex-direction:column; gap:12px;",
        ),
        width="360px",
        style="background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%); border-right: 1px solid #e2e8f0; padding: 24px 20px; overflow-y:auto;",
    ),
    # Global CSS
    ui.tags.style(
        """
    html, body { margin: 0; padding: 0; overflow: hidden; height: 100%; }
    body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f1f5f9; }
    .bslib-page-sidebar, .bslib-sidebar-layout, .main, .bslib-page-sidebar > .container-fluid,
    .bslib-sidebar-layout > .main { overflow: hidden !important; height: 100%; }
    .sidebar { background-color: #f8fafc !important; border-right: 1px solid #e2e8f0 !important; }
    .nav-tabs { border-bottom: 2px solid #e2e8f0; }
    .nav-tabs .nav-link { color: #475569; font-weight: 500; border: none; border-radius: 6px 6px 0 0; margin-right: 4px; padding: 10px 16px; }
    .nav-tabs .nav-link.active { background-color: #1e293b; color: white; }
    .nav-tabs .nav-link:hover { background-color: #e2e8f0; color: #1e293b; }
    .form-check-input:checked { background-color: #1e293b; border-color: #1e293b; }
    .form-select { border-radius: 6px; border: 1px solid #cbd5e1; }
    .form-control { border-radius: 6px; border: 1px solid #cbd5e1; }
    .btn { border-radius: 6px; }
    .card { border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }

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
    .information p { margin: 0 0 12px 0; line-height: 1.6; }
    .logo-cap { margin:8px 0 0 0; font-size:12px; opacity:.7; color: #64748b; }
    .leaflet-control-layers { display: none !important; }

    /* Sticky header + pinned first column for data tables */
    .sticky-wrap { overflow: visible; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
    table.sticky { border-collapse: separate; border-spacing: 0; border-radius: 8px; overflow: hidden; }
    table.sticky thead th {
      position: sticky; top: 0; background: #f1f5f9;
      z-index: 2; box-shadow: inset 0 -1px 0 #cbd5e1; font-weight: 600; color: #374151;
    }
    table.sticky td:first-child,
    table.sticky th:first-child {
      position: sticky; left: 0; background: #ffffff;
      z-index: 1; box-shadow: inset -1px 0 0 #e2e8f0;
    }
    table.sticky thead th:first-child { z-index: 3; }
    table.sticky td, table.sticky th { padding: 8px 12px; border-bottom: 1px solid #e2e8f0; }
    table.sticky tbody tr:hover { background-color: #f8fafc; }

    /* Enhanced Sidebar Filters */
    .filter-sections {
        display: flex;
        flex-direction: column;
        gap: 12px;
    }

    .filter-section {
        background: white;
        border-radius: 8px;
        padding: 14px;
        border: 1px solid #e2e8f0;
        transition: all 0.2s ease;
    }

    .filter-section:hover {
        border-color: #cbd5e1;
        box-shadow: 0 2px 4px rgba(15, 23, 42, 0.04);
    }

    .filter-section-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 8px;
    }

    /* Checkbox styling */
    .shiny-input-checkboxgroup {
        display: flex;
        flex-direction: column;
        gap: 8px;
    }

    .form-check {
        display: flex;
        align-items: center;
        margin: 0;
        padding: 6px 8px;
        border-radius: 6px;
        transition: all 0.15s ease;
    }

    .form-check:hover {
        background-color: #f0f9ff;
    }

    .form-check-input {
        width: 18px;
        height: 18px;
        margin-right: 8px;
        border: 2px solid #cbd5e1;
        border-radius: 4px;
        cursor: pointer;
        transition: all 0.2s ease;
        flex-shrink: 0;
    }

    .form-check-input:hover {
        border-color: #1e293b;
        box-shadow: 0 0 0 3px rgba(30, 41, 59, 0.1);
    }

    .form-check-input:checked {
        background-color: #1e293b;
        border-color: #1e293b;
        box-shadow: inset 0 0 0 2px white;
    }

    .form-check-label {
        font-size: 14px;
        color: #374151;
        font-weight: 400;
        cursor: pointer;
        margin: 0;
        user-select: none;
        flex: 1;
    }

    .form-check-input:checked ~ .form-check-label {
        color: #1e293b;
        font-weight: 500;
    }

    /* Search input styling */
    .shiny-input-container input[type="text"] {
        width: 100%;
        padding: 10px 12px;
        border: 1.5px solid #e2e8f0;
        border-radius: 6px;
        font-size: 14px;
        color: #374151;
        background-color: #ffffff;
        transition: all 0.2s ease;
        font-family: inherit;
    }

    .shiny-input-container input[type="text"]:focus {
        outline: none;
        border-color: #1e293b;
        box-shadow: 0 0 0 3px rgba(30, 41, 59, 0.1);
        background-color: white;
    }

    .shiny-input-container input[type="text"]::placeholder {
        color: #cbd5e1;
    }

    /* Selectize styling */
    .selectize-control.single .selectize-input {
        border-radius: 6px;
        border: 1.5px solid #e2e8f0;
        padding: 8px 12px;
        transition: all 0.2s ease;
        font-size: 14px;
        min-height: 40px;
    }

    .selectize-control.single .selectize-input:focus {
        border-color: #1e293b;
        box-shadow: 0 0 0 3px rgba(30, 41, 59, 0.1);
    }

    .selectize-control .selectize-input > div {
        padding: 4px 6px;
        border-radius: 4px;
        background: #f0f9ff;
        color: #1e293b;
        font-size: 13px;
    }

    .selectize-control .selectize-input > div [data-value]:not(:first-child) {
        margin-left: 4px;
    }

    .selectize-dropdown {
        border-radius: 6px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 4px 12px rgba(15, 23, 42, 0.1);
    }

    .selectize-dropdown-content {
        border-radius: 6px;
    }

    .selectize-dropdown-content .option {
        padding: 8px 12px;
        font-size: 14px;
        color: #374151;
        transition: all 0.15s ease;
    }

    .selectize-dropdown-content .option:hover {
        background-color: #f0f9ff;
        color: #1e293b;
    }

    .selectize-dropdown-content .option.selected {
        background-color: #1e293b;
        color: white;
    }

    /* Scrollbar styling for sidebar */
    .bslib-sidebar::-webkit-scrollbar {
        width: 6px;
    }

    .bslib-sidebar::-webkit-scrollbar-track {
        background: transparent;
    }

    .bslib-sidebar::-webkit-scrollbar-thumb {
        background: #cbd5e1;
        border-radius: 3px;
    }

    .bslib-sidebar::-webkit-scrollbar-thumb:hover {
        background: #94a3b8;
    }

    /* Firefox scrollbar */
    .bslib-sidebar {
        scrollbar-color: #cbd5e1 transparent;
        scrollbar-width: thin;
    }

    /* Tab-specific overflow settings */
    .tab-content { overflow: visible; height: auto; }
    .tab-pane { overflow: visible; height: auto; }
    
    /* Data and Information tabs should scroll */
    .tab-pane[data-value="Data"],
    .tab-pane[data-value="Information"] {
        overflow-y: auto;
        max-height: calc(100vh - 128px);
        padding: 16px;
    }
    
    /* Map tab keeps fixed layout without scrolling */
    .tab-pane[data-value="Map"] {
        overflow: hidden;
        height: 100%;
        padding: 0;
    }
    """
    ),
    # Main content
    ui.navset_tab(
        ui.nav_panel(
            "Map",
            ui.tags.div(
                {"id": "map-split-container", "style": "display:flex;flex-direction:column;height:calc(100vh - 128px);min-height:360px;"},
                ui.tags.div(
                    {"id": "map-pane", "style": "position:relative;flex:0 0 60%;min-height:220px;"},
                    output_widget("m", height="100%"),
                ),
                ui.tags.div(
                    {"id": "map-resizer", "style": "height:8px;cursor:row-resize;background:rgba(0,0,0,0.08);"},
                ),
                ui.tags.div(
                    {"id": "bottom-pane", "style": "flex:1 1 auto;overflow:auto;min-height:150px;padding:16px;background-color:#ffffff;border-radius:0 0 8px 8px;box-shadow:0 1px 3px rgba(0,0,0,0.1);"},
                    ui.HTML("<div style='font-weight:600;margin:0 0 8px 0;font-size:16px;color:#1e293b'>Selected projects</div>"),
                    ui.output_ui("clicked_table"),
                ),
            ),
        ),
        ui.nav_panel(
            "Data",
            ui.layout_columns(
                ui.div(
                    ui.input_text("data_search", "Search (all attributes)", placeholder="Type to filter (case-insensitive)"),
                    style="margin-bottom:0px;",
                ),
                col_widths=(12,),
            ),
            ui.output_ui("table_data"),
        ),
        ui.nav_panel(
            "Information",
            ui.div(
                {"class": "information", "style": "padding:24px; line-height:1.6; max-width:980px; background-color:#ffffff; border-radius:8px; box-shadow:0 1px 3px rgba(0,0,0,0.1); margin:16px 0;"},
                ui.output_ui("information_content"),
                ui.tags.hr(style="margin:24px 0; border-top:2px solid #e2e8f0"),
                ui.output_ui("logos"),
            ),
        ),
    ),
    # Title and window title scripts
    ui.tags.script(
        """
        var checkTitle = setInterval(function() {
            if (document.title !== "Risk-Related Projects") {
                document.title = "Risk-Related Projects";
            } else {
                clearInterval(checkTitle);
            }
        }, 100);
        """
    ),
    ui.tags.script(
        """
        (function() {
            var resizer = document.getElementById('map-resizer');
            var container = document.getElementById('map-split-container');
            var top = document.getElementById('map-pane');
            if (!resizer || !container || !top) return;

            var startY = 0;
            var startTopHeight = 0;
            var minTop = 120;
            var minBottom = 120;

            function onMouseMove(e) {
                var dy = e.clientY - startY;
                var containerRect = container.getBoundingClientRect();
                var maxTop = containerRect.height - minBottom - resizer.offsetHeight;
                var newTopHeight = Math.min(Math.max(startTopHeight + dy, minTop), maxTop);
                top.style.flex = '0 0 ' + newTopHeight + 'px';
                var bottom = document.getElementById('bottom-pane');
                if (bottom) {
                    bottom.style.flex = '1 1 auto';
                }
            }

            function onMouseUp() {
                document.removeEventListener('mousemove', onMouseMove);
                document.removeEventListener('mouseup', onMouseUp);
                window.dispatchEvent(new Event('resize'));
            }

            resizer.addEventListener('mousedown', function(e) {
                e.preventDefault();
                startY = e.clientY;
                startTopHeight = top.getBoundingClientRect().height;
                document.addEventListener('mousemove', onMouseMove);
                document.addEventListener('mouseup', onMouseUp);
            });
        })();
        """
    ),
    title="Mainland Coast Salish Area Risk-Related Projects Database",
    window_title="Risk-Related Projects",
)
