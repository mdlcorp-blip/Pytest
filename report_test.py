import os
import json
import copy

TESTCASES_DIR = r"C:\test_json"
OUTPUT_PREFIX = r"C:\test_json\viewer_"

# Hardcoded presets (you can edit these)
PRESETS = {
    "All fields": [],  # special: no filtering
    "Order Summary": ["order.id", "order.items", "customer.email"],
    "Customer Only": ["customer"],
    "Metadata Only": ["metadata"]
}


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_test_cases(folder):
    files = [f for f in os.listdir(folder) if f.lower().endswith(".json")]

    requests = [
        f for f in files
        if not f.startswith("Result for ") and not f.endswith(" after.json")
    ]

    test_cases = {}

    for req in requests:
        base = req[:-5]
        before = f"Result for {base}.json"
        after = f"Result for {base} after.json"

        if before in files and after in files:
            test_cases[base] = {
                "requestFile": req,
                "beforeFile": before,
                "afterFile": after,
                "request": load_json(os.path.join(folder, req)),
                "before": load_json(os.path.join(folder, before)),
                "after": load_json(os.path.join(folder, after)),
            }

    return test_cases


def merge_missing(before, after):
    """
    Ensures both BEFORE and AFTER have identical structure.
    Missing fields become null.
    """

    def merge(a, b):
        if isinstance(a, dict) and isinstance(b, dict):
            keys = set(a.keys()) | set(b.keys())
            out_a = {}
            out_b = {}
            for k in keys:
                va = a.get(k, None)
                vb = b.get(k, None)
                if isinstance(va, dict) and isinstance(vb, dict):
                    ma, mb = merge(va, vb)
                    out_a[k] = ma
                    out_b[k] = mb
                else:
                    out_a[k] = va if va is not None else None
                    out_b[k] = vb if vb is not None else None
            return out_a, out_b

        return a, b

    return merge(before, after)


def get_subtree(obj, path_parts):
    """Return subtree at path_parts, or None if not found."""
    cur = obj
    for p in path_parts:
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return cur


def set_subtree(target, path_parts, subtree):
    """Set subtree at path_parts in target, creating dicts as needed."""
    cur = target
    for p in path_parts[:-1]:
        if p not in cur or not isinstance(cur[p], dict):
            cur[p] = {}
        cur = cur[p]
    cur[path_parts[-1]] = subtree


def filter_by_paths(obj, paths):
    """
    F2 behavior: for each path, keep the entire subtree under it.
    paths: list of "a.b.c" strings.
    If paths is empty, return obj unchanged.
    """
    if not paths:
        return obj

    if not isinstance(obj, dict):
        return obj

    result = {}
    for path in paths:
        parts = path.split(".")
        subtree = get_subtree(obj, parts)
        if subtree is not None:
            set_subtree(result, parts, subtree)
    return result


def generate_html(name, tc):
    # Filtering is done in JS, but we need presets list there
    js_request = json.dumps(tc["request"], ensure_ascii=False)
    js_before = json.dumps(tc["before"], ensure_ascii=False)
    js_after = json.dumps(tc["after"], ensure_ascii=False)
    js_presets = json.dumps(PRESETS, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Viewer - {name}</title>

<style>
body {{
    font-family: Arial, sans-serif;
    padding: 20px;
}}

.tabs {{
    display: flex;
    border-bottom: 2px solid #ccc;
    margin-bottom: 10px;
}}

.tab {{
    padding: 10px 20px;
    cursor: pointer;
    border: 1px solid #ccc;
    border-bottom: none;
    background: #eee;
    margin-right: 5px;
}}

.tab.active {{
    background: white;
    font-weight: bold;
}}

.tab-content {{
    display: none;
}}

.tab-content.active {{
    display: block;
}}

.layout {{
    display: flex;
    gap: 20px;
}}

.selector-col {{
    width: 20%;
    min-width: 200px;
}}

.viewer-col {{
    width: 40%;
}}

.req-selector-col {{
    width: 30%;
}}

.req-viewer-col {{
    width: 70%;
}}

.panel {{
    border: 1px solid #ccc;
    padding: 10px;
    background: #f9f9f9;
}}

.summary-panel {{
    border: 2px solid #888;
    background: #f0f0f0;
    padding: 10px;
    margin-bottom: 15px;
}}

.summary-header {{
    font-weight: bold;
    cursor: pointer;
}}

.summary-list {{
    margin-top: 8px;
    padding-left: 20px;
    display: none;
}}

.filter-panel {{
    border: 2px solid #555;
    background: #f5f5ff;
    padding: 10px;
    margin-bottom: 15px;
}}

.filter-row {{
    margin: 5px 0;
}}

.tree-node {{
    margin-left: 16px;
}}

pre {{
    background: #f7f7f7;
    padding: 8px;
    border: 1px solid #ccc;
    overflow-x: auto;
    white-space: pre;
}}

.field-label {{
    font-family: monospace;
}}

.checkbox-node {{
    margin: 2px 0;
}}
</style>

<script>
var RAW_REQUEST = {js_request};
var RAW_BEFORE = {js_before};
var RAW_AFTER = {js_after};
var PRESETS = {js_presets};

var REQUEST = null;
var BEFORE = null;
var AFTER = null;

var selectedRequestFields = new Set();
var selectedSharedFields = new Set();

function deepCopy(obj) {{
    return JSON.parse(JSON.stringify(obj));
}}

function getSubtree(obj, parts) {{
    var cur = obj;
    for (var i = 0; i < parts.length; i++) {{
        if (cur === null || typeof cur !== "object" || Array.isArray(cur)) return null;
        if (!(parts[i] in cur)) return null;
        cur = cur[parts[i]];
    }}
    return cur;
}}

function setSubtree(target, parts, subtree) {{
    var cur = target;
    for (var i = 0; i < parts.length - 1; i++) {{
        var p = parts[i];
        if (!(p in cur) || typeof cur[p] !== "object" || cur[p] === null || Array.isArray(cur[p])) {{
            cur[p] = {{}};
        }}
        cur = cur[p];
    }}
    cur[parts[parts.length - 1]] = subtree;
}}

function filterByPaths(obj, paths) {{
    if (!paths || paths.length === 0) return obj;
    if (obj === null || typeof obj !== "object" || Array.isArray(obj)) return obj;

    var result = {{}};
    paths.forEach(function(path) {{
        var parts = path.split(".");
        var subtree = getSubtree(obj, parts);
        if (subtree !== null && subtree !== undefined) {{
            setSubtree(result, parts, subtree);
        }}
    }});
    return result;
}}

function mergeMissing(before, after) {{
    function merge(a, b) {{
        if (a && typeof a === "object" && !Array.isArray(a) &&
            b && typeof b === "object" && !Array.isArray(b)) {{
            var keys = new Set(Object.keys(a).concat(Object.keys(b)));
            var outA = {{}};
            var outB = {{}};
            keys.forEach(function(k) {{
                var va = a.hasOwnProperty(k) ? a[k] : null;
                var vb = b.hasOwnProperty(k) ? b[k] : null;
                if (va && typeof va === "object" && !Array.isArray(va) &&
                    vb && typeof vb === "object" && !Array.isArray(vb)) {{
                    var pair = merge(va, vb);
                    outA[k] = pair[0];
                    outB[k] = pair[1];
                }} else {{
                    outA[k] = (va !== undefined && va !== null) ? va : null;
                    outB[k] = (vb !== undefined && vb !== null) ? vb : null;
                }}
            }});
            return [outA, outB];
        }}
        return [a, b];
    }}
    return merge(before, after);
}}

function applyFilter() {{
    var presetSelect = document.getElementById("presetSelect");
    var manualInput = document.getElementById("manualFilter");
    var presetName = presetSelect.value;
    var manualText = manualInput.value.trim();

    var presetPaths = [];
    if (presetName && PRESETS[presetName]) {{
        presetPaths = PRESETS[presetName];
    }}

    var manualPaths = [];
    if (manualText.length > 0) {{
        manualPaths = manualText.split(",").map(function(s) {{
            return s.trim();
        }}).filter(function(s) {{ return s.length > 0; }});
    }}

    var paths = manualPaths.length > 0 ? manualPaths : presetPaths;

    REQUEST = filterByPaths(deepCopy(RAW_REQUEST), paths);
    var filteredBefore = filterByPaths(deepCopy(RAW_BEFORE), paths);
    var filteredAfter = filterByPaths(deepCopy(RAW_AFTER), paths);

    var pair = mergeMissing(filteredBefore, filteredAfter);
    BEFORE = pair[0];
    AFTER = pair[1];

    render();
}}

function createElement(tag, attrs, text) {{
    var el = document.createElement(tag);
    if (attrs) {{
        for (var k in attrs) {{
            if (k === "class") el.className = attrs[k];
            else if (k === "onclick") el.onclick = attrs[k];
            else el.setAttribute(k, attrs[k]);
        }}
    }}
    if (text !== undefined && text !== null) {{
        el.appendChild(document.createTextNode(text));
    }}
    return el;
}}

function pathToString(path) {{
    return path.join(".");
}}

function updateSummary(panelId, listId, selectedSet) {{
    var panel = document.getElementById(panelId);
    var list = document.getElementById(listId);

    var count = selectedSet.size;
    panel.textContent = "Selected fields (" + count + ") ▶";

    list.innerHTML = "";
    var arr = Array.from(selectedSet).sort();
    arr.forEach(f => {{
        var li = createElement("div", null, "- " + f);
        list.appendChild(li);
    }});
}}

function toggleSummary(listId, headerId) {{
    var list = document.getElementById(listId);
    var header = document.getElementById(headerId);
    if (list.style.display === "none" || list.style.display === "") {{
        list.style.display = "block";
        header.textContent = header.textContent.replace("▶", "▼");
    }} else {{
        list.style.display = "none";
        header.textContent = header.textContent.replace("▼", "▶");
    }}
}}

function pathToId(prefix, path) {{
    return prefix + "_" + path.join("__");
}}

function buildSelectorTree(container, obj, path, callback, selectedSet, summaryPanelId, summaryListId) {{
    if (obj !== null && typeof obj === "object" && !Array.isArray(obj)) {{
        Object.keys(obj).forEach(function(key) {{
            var childPath = path.concat([key]);
            var value = obj[key];

            var node = createElement("div", {{class: "tree-node"}});
            var cb = createElement("input", {{type: "checkbox"}});
            cb.checked = true;

            var fullPath = pathToString(childPath);
            selectedSet.add(fullPath);

            cb.onclick = function() {{
                if (cb.checked) selectedSet.add(fullPath);
                else selectedSet.delete(fullPath);

                updateSummary(summaryPanelId, summaryListId, selectedSet);
                callback(childPath, cb.checked);
            }};

            var label = createElement("span", {{class: "field-label"}}, " " + key);

            var row = createElement("div", {{class: "checkbox-node"}});
            row.appendChild(cb);
            row.appendChild(label);
            node.appendChild(row);

            if (value !== null && typeof value === "object") {{
                buildSelectorTree(node, value, childPath, callback, selectedSet, summaryPanelId, summaryListId);
            }}

            container.appendChild(node);
        }});
    }}
}}

function buildJsonView(container, obj, prefix, path) {{
    if (obj !== null && typeof obj === "object" && !Array.isArray(obj)) {{
        Object.keys(obj).forEach(function(key) {{
            var childPath = path.concat([key]);
            var value = obj[key];
            var id = pathToId(prefix, childPath);

            var wrapper = createElement("div", {{id: id, class: "panel"}});
            var label = createElement("div", {{class: "field-label"}}, childPath.join("."));
            wrapper.appendChild(label);

            var pre = createElement("pre");
            pre.textContent = JSON.stringify(value, null, 2);
            wrapper.appendChild(pre);

            container.appendChild(wrapper);

            if (value !== null && typeof value === "object") {{
                buildJsonView(container, value, prefix, childPath);
            }}
        }});
    }}
}}

function hideField(prefix, path, visible) {{
    var id = pathToId(prefix, path);
    var el = document.getElementById(id);
    if (el) {{
        el.style.display = visible ? "block" : "none";
    }}
}}

function hideRecursive(prefix, obj, path, visible) {{
    hideField(prefix, path, visible);

    if (obj !== null && typeof obj === "object") {{
        Object.keys(obj).forEach(function(key) {{
            hideRecursive(prefix, obj[key], path.concat([key]), visible);
        }});
    }}
}}

function applySharedHide(path, visible) {{
    hideRecursive("before", BEFORE, path, visible);
    hideRecursive("after", AFTER, path, visible);
}}

function render() {{
    var reqSel = document.getElementById("reqSelector");
    var reqView = document.getElementById("reqViewer");

    var sharedSel = document.getElementById("sharedSelector");
    var beforeView = document.getElementById("beforeViewer");
    var afterView = document.getElementById("afterViewer");

    reqSel.innerHTML = "";
    reqView.innerHTML = "";
    sharedSel.innerHTML = "";
    beforeView.innerHTML = "";
    afterView.innerHTML = "";

    selectedRequestFields.clear();
    selectedSharedFields.clear();

    buildSelectorTree(
        reqSel, REQUEST, [],
        function(path, visible) {{ hideRecursive("req", REQUEST, path, visible); }},
        selectedRequestFields,
        "reqSummaryHeader",
        "reqSummaryList"
    );

    buildJsonView(reqView, REQUEST, "req", []);

    buildSelectorTree(
        sharedSel, BEFORE, [],
        function(path, visible) {{ applySharedHide(path, visible); }},
        selectedSharedFields,
        "sharedSummaryHeader",
        "sharedSummaryList"
    );

    buildJsonView(beforeView, BEFORE, "before", []);
    buildJsonView(afterView, AFTER, "after", []);

    updateSummary("reqSummaryHeader", "reqSummaryList", selectedRequestFields);
    updateSummary("sharedSummaryHeader", "sharedSummaryList", selectedSharedFields);
}}

function switchTab(tab) {{
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));

    document.getElementById("tab_" + tab).classList.add("active");
    document.getElementById("content_" + tab).classList.add("active");
}}

window.onload = function() {{
    // Populate presets dropdown
    var presetSelect = document.getElementById("presetSelect");
    Object.keys(PRESETS).forEach(function(name) {{
        var opt = document.createElement("option");
        opt.value = name;
        opt.textContent = name;
        presetSelect.appendChild(opt);
    }});

    // Default: use "All fields" if present, else no filter
    if (PRESETS["All fields"]) {{
        presetSelect.value = "All fields";
    }}

    applyFilter();
    switchTab("request");
}};
</script>

</head>
<body>

<h2>Test Case: {name}</h2>

<div class="filter-panel">
    <div class="filter-row">
        <strong>Preset filters:</strong>
        <select id="presetSelect"></select>
        <button onclick="applyFilter()">Apply Preset</button>
    </div>
    <div class="filter-row">
        <strong>Or load only these fields (comma-separated paths):</strong><br>
        <input id="manualFilter" type="text" style="width: 80%;" placeholder="order.id, order.items, customer.email">
        <button onclick="applyFilter()">Apply Manual Filter</button>
    </div>
</div>

<div class="tabs">
    <div id="tab_request" class="tab active" onclick="switchTab('request')">Request</div>
    <div id="tab_compare" class="tab" onclick="switchTab('compare')">Current vs After</div>
</div>

<!-- REQUEST TAB -->
<div id="content_request" class="tab-content active">

    <div class="summary-panel">
        <div id="reqSummaryHeader" class="summary-header"
             onclick="toggleSummary('reqSummaryList', 'reqSummaryHeader')">
            Selected fields (0) ▶
        </div>
        <div id="reqSummaryList" class="summary-list"></div>
    </div>

    <div class="layout">
        <div class="req-selector-col panel">
            <h3>Request Selector</h3>
            <div id="reqSelector"></div>
        </div>
        <div class="req-viewer-col panel">
            <h3>Request JSON</h3>
            <div id="reqViewer"></div>
        </div>
    </div>
</div>

<!-- COMPARE TAB -->
<div id="content_compare" class="tab-content">

    <div class="summary-panel">
        <div id="sharedSummaryHeader" class="summary-header"
             onclick="toggleSummary('sharedSummaryList', 'sharedSummaryHeader')">
            Selected fields (0) ▶
        </div>
        <div id="sharedSummaryList" class="summary-list"></div>
    </div>

    <div class="layout">
        <div class="selector-col panel">
            <h3>Shared Selector</h3>
            <div id="sharedSelector"></div>
        </div>
        <div class="viewer-col panel">
            <h3>Current (BEFORE)</h3>
            <div id="beforeViewer"></div>
        </div>
        <div class="viewer-col panel">
            <h3>After</h3>
            <div id="afterViewer"></div>
        </div>
    </div>
</div>

</body>
</html>
"""
    return html


def main():
    test_cases = find_test_cases(TESTCASES_DIR)
    if not test_cases:
        print("No test cases found.")
        return

    for name, tc in test_cases.items():
        html = generate_html(name, tc)
        filename = f"{OUTPUT_PREFIX}{name}.html"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"Generated: {filename}")


if __name__ == "__main__":
    main()
