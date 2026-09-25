"""simulation.py - logical network simulation for SubnetX.

Educational model only: one router, one switch per department and up to
MAX_PCS simulated PCs per department. Nothing is sent over a real network.

Simplification: the router stands for the gateway between the subnets, but its
interface (gateway) IP addresses are not modelled. Hosts take their addresses
directly from the usable range of their subnet, starting at the first usable IP.

Flow: build_topology(subnets) -> send_packet(...) -> topology_html(...) to draw.
"""
import html as html_lib
import ipaddress
import re

ROUTER = "Router"
CUSTOM_IP = "Custom IP address..."
MAX_PCS = 4   # PC slots per department; larger ones show MAX_PCS - 1 PCs + "+N more"


# ------------------------------------------------------------------ topology
def build_topology(subnets):
    """Build the router / switch / PC model from the VLSM result rows.

    A department with up to MAX_PCS requested hosts gets one PC per host.
    A larger one gets its first MAX_PCS - 1 hosts as PCs; the rest are only
    counted ("hidden") so the diagram stays readable."""
    departments, devices, used = [], {}, set()
    for s in subnets:
        # short PC prefix, e.g. "AI/ML" -> "AIML" (kept unique)
        base = re.sub(r"[^A-Za-z0-9]", "", s["Department"]) or "DEPT"
        prefix, n = base, 2
        while prefix in used:
            prefix, n = f"{base}{n}", n + 1
        used.add(prefix)

        network = ipaddress.IPv4Network(f'{s["Network"]}{s["CIDR"]}')
        first = ipaddress.IPv4Address(s["First IP"])
        required = s["Required"]
        shown = required if required <= MAX_PCS else MAX_PCS - 1
        dept = {
            "name": s["Department"],
            "switch": f'{s["Department"]} Switch',
            "network": network,
            "cidr": s["CIDR"],
            "capacity": s["Allocated"],
            "devices": [],
            "hidden": required - shown,          # requested hosts not simulated
            "hidden_range": ((first + shown, first + required - 1)
                             if required > shown else None),
        }
        for k in range(shown):             # PC1 gets the first usable IP
            name = f"{prefix}-PC{k + 1}"
            devices[name] = {"ip": str(first + k), "dept": dept}   # from the real subnet
            dept["devices"].append(name)
        departments.append(dept)
    return {"router": ROUTER, "departments": departments, "devices": devices}


def all_node_names(topo):
    """Every router / switch / device name (used for the 'disable' option)."""
    names = [topo["router"]] + [d["switch"] for d in topo["departments"]]
    return names + list(topo["devices"])


# ------------------------------------------------------------------- packets
def send_packet(topo, src_name, dst, disabled=()):
    """Simulate one packet.

    dst is a device name or an IP string. Returns a dict with:
    status, source_ip, dest_ip, path (planned), reached (nodes it got through),
    failed_at, reason.
    """
    devices = topo["devices"]
    src = devices[src_name]
    result = {"status": "FAILED", "source": src_name, "source_ip": src["ip"],
              "dest_ip": "", "path": [], "reached": [], "failed_at": None,
              "reason": ""}

    # 1. find the destination device / subnet
    dst_name = dst if dst in devices else None
    if dst_name is None:
        try:
            ip = ipaddress.IPv4Address(str(dst).strip())
        except ValueError:
            result["reason"] = "Invalid destination IP address."
            return result
        result["dest_ip"] = str(ip)
        for name, dev in devices.items():
            if dev["ip"] == str(ip):
                dst_name = name
        dst_dept = next((d for d in topo["departments"] if ip in d["network"]), None)
    else:
        result["dest_ip"] = devices[dst_name]["ip"]
        dst_dept = devices[dst_name]["dept"]

    # 2. plan the path (same subnet -> switch only, else via the router)
    src_dept = src["dept"]
    path = [src_name, src_dept["switch"]]
    if dst_dept is None:
        path.append(topo["router"])
        end_reason = "Destination unreachable: no route to that network."
    elif dst_dept is src_dept:
        end_reason = None
    else:
        path += [topo["router"], dst_dept["switch"]]
        end_reason = None
    if dst_dept is not None:
        hidden = dst_dept["hidden_range"]
        if dst_name:
            path.append(dst_name)
        elif ip == dst_dept["network"].network_address:
            end_reason = (f"{ip} is the network address of the {dst_dept['name']} "
                          f"subnet, not a host address.")
        elif ip == dst_dept["network"].broadcast_address:
            end_reason = (f"{ip} is the broadcast address of the {dst_dept['name']} "
                          f"subnet, not a simulated host destination "
                          f"(broadcast delivery is not modelled).")
        elif hidden and hidden[0] <= ip <= hidden[1]:
            end_reason = (f"{ip} belongs to one of the {dst_dept['hidden']} requested "
                          f"{dst_dept['name']} hosts that are not simulated. "
                          f"Only the PCs shown in the diagram can receive packets.")
        else:
            end_reason = "Destination unreachable: no device with that IP."
    result["path"] = path

    # 3. walk the path, stopping at the first disabled node
    for node in path:
        if node in disabled:
            result["failed_at"] = node
            if node == src_name:
                result["reason"] = f"Source device {node} is down."
            elif node == dst_name:
                result["reason"] = f"Destination unreachable: {node} is down."
            else:
                result["reason"] = f"{node} is down, the packet cannot pass."
            return result
        result["reached"].append(node)

    if end_reason:
        result["failed_at"] = path[-1]
        result["reason"] = end_reason
        return result
    result["status"] = "DELIVERED"
    return result


# ------------------------------------------------------------------- diagram
# The diagram is drawn as inline SVG (icons are Lucide paths, ISC licence) and
# shown inside an iframe, so it needs no extra library and no emojis.
ICONS = {
    "router": '<rect width="20" height="8" x="2" y="14" rx="2"/><path d="M6.01 18H6"/><path d="M10.01 18H10"/><path d="M15 10v4"/><path d="M17.84 7.17a4 4 0 0 0-5.66 0"/><path d="M20.66 4.34a8 8 0 0 0-11.31 0"/>',
    "switch": '<rect x="16" y="16" width="6" height="6" rx="1"/><rect x="2" y="16" width="6" height="6" rx="1"/><rect x="9" y="2" width="6" height="6" rx="1"/><path d="M5 16v-3a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v3"/><path d="M12 12V8"/>',
    "pc": '<rect width="20" height="14" x="2" y="3" rx="2"/><line x1="8" x2="16" y1="21" y2="21"/><line x1="12" x2="12" y1="17" y2="21"/>',
    "send": '<path d="M14.536 21.686a.5.5 0 0 0 .937-.024l6.5-19a.496.496 0 0 0-.635-.635l-19 6.5a.5.5 0 0 0-.024.937l7.93 3.18a2 2 0 0 1 1.112 1.11z"/><path d="m21.854 2.147-10.94 10.939"/>',
    "ok": '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
    "fail": '<circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/>',
    "alert": '<circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/>',
    "down": '<path d="M12 5v14"/><path d="m19 12-7 7-7-7"/>',
}
NAVY, BLUE, TEAL, RED, GRAY = "#0f2942", "#2563eb", "#0d9488", "#dc2626", "#64748b"

# layout numbers (SVG pixels)
PC_W, PC_H, PC_GAP = 90, 74, 6
SW_W, SW_H = 186, 84
RT_W, RT_H = 220, 78
GROUP_GAP, PAD = 14, 10
RT_Y, GROUP_Y, GROUP_H, SW_Y, PC_Y = 8, 132, 240, 160, 282
SVG_H = 384


def _esc(text):
    return html_lib.escape(str(text), quote=True)


def _clip(text, n):
    text = str(text)
    return text if len(text) <= n else text[:n - 1] + "…"


def _icon(name, x, y, size, color, width=2):
    k = size / 24
    return (f'<g transform="translate({x:.1f},{y:.1f}) scale({k:.3f})" fill="none" '
            f'stroke="{color}" stroke-width="{width}" stroke-linecap="round" '
            f'stroke-linejoin="round">{ICONS[name]}</g>')


def _i(name, size, color):
    """Small standalone icon for the status panel."""
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
            f'stroke="{color}" stroke-width="2" stroke-linecap="round" '
            f'stroke-linejoin="round">{ICONS[name]}</svg>')


def _more_key(d):
    """Layout key of a department's "+N more hosts" card (not a real node)."""
    return ("more", d["name"])


def _layout(topo):
    """Positions of every node: {name: (center_x, top, bottom)} and the SVG width."""
    deps = topo["departments"]
    slots = [len(d["devices"]) + (1 if d["hidden"] else 0) for d in deps]
    widths = [max(SW_W, m * PC_W + (m - 1) * PC_GAP) + 20 for m in slots]
    total = sum(widths) + (len(deps) - 1) * GROUP_GAP
    width = max(total + 2 * PAD, 240)
    pos = {topo["router"]: (width / 2, RT_Y, RT_Y + RT_H)}
    groups = []
    gx = (width - total) / 2
    for d, gw, m in zip(deps, widths, slots):
        cx = gx + gw / 2
        pos[d["switch"]] = (cx, SW_Y, SW_Y + SW_H)
        start = cx - (m * PC_W + (m - 1) * PC_GAP) / 2
        cards = d["devices"] + ([_more_key(d)] if d["hidden"] else [])
        for j, name in enumerate(cards):
            pos[name] = (start + j * (PC_W + PC_GAP) + PC_W / 2, PC_Y, PC_Y + PC_H)
        groups.append((d, gx, gw))
        gx += gw + GROUP_GAP
    return pos, groups, width


def _edge_path(pos, a, b):
    """Elbow path from the upper node's bottom to the lower node's top."""
    if pos[a][1] > pos[b][1]:
        a, b = b, a
    (ax, _, ab), (bx, bt, _) = pos[a], pos[b]
    mid = (ab + bt) / 2
    return f"M{ax:.1f} {ab:.1f} V{mid:.1f} H{bx:.1f} V{bt:.1f}"


def _state(packet, hop, final):
    """Which nodes / links are done, current, next, active or failed."""
    st = {"done": set(), "current": None, "next": None, "prev": None, "failed": None,
          "last_ok": None, "done_links": [], "next_links": [], "failed_links": [],
          "active_links": []}
    if not packet:
        return st
    path, reached = packet["path"], packet["reached"]
    if final:
        st["done"] = set(reached)
        st["done_links"] = list(zip(reached, reached[1:]))
        st["failed"] = packet["failed_at"]
        if packet["status"] == "DELIVERED":
            st["last_ok"] = reached[-1]
        elif packet["failed_at"] not in reached and reached:
            st["failed_links"] = [(reached[-1], packet["failed_at"])]
        return st
    st["current"] = reached[hop]
    st["done"] = set(reached[:hop])
    st["done_links"] = list(zip(reached[:hop], reached[1:hop]))
    if hop > 0:
        st["prev"] = reached[hop - 1]
        st["active_links"] = [(reached[hop - 1], reached[hop])]
    if hop + 1 < len(path):
        st["next"] = path[hop + 1]
        st["next_links"] = [(reached[hop], path[hop + 1])]
    return st


def _svg(topo, disabled, st):
    pos, groups, width = _layout(topo)
    router = topo["router"]
    devices = topo["devices"]

    # links, drawn in layers so highlighted ones sit on top
    all_links = [(router, d["switch"]) for d in topo["departments"]]
    all_links += [(d["switch"], n) for d in topo["departments"] for n in d["devices"]]
    all_links += [(d["switch"], _more_key(d)) for d in topo["departments"] if d["hidden"]]
    layers = [("#cbd5e1", 1.5, "", all_links),
              (TEAL, 3, "", st["done_links"]),
              ("#93c5fd", 2.5, "6 5", st["next_links"]),
              (RED, 3, "6 5", st["failed_links"]),
              (BLUE, 4.5, "", st["active_links"])]
    out = [f'<svg viewBox="0 0 {width:.0f} {SVG_H}" xmlns="http://www.w3.org/2000/svg" '
           f'style="width:100%;max-width:{width:.0f}px;height:auto;display:block;margin:0 auto" '
           f'font-family="Segoe UI, Helvetica, Arial, sans-serif">',
           '<defs><filter id="sh" x="-10%" y="-10%" width="120%" height="130%">'
           '<feDropShadow dx="0" dy="1" stdDeviation="2" flood-color="#0f2942" '
           'flood-opacity="0.12"/></filter></defs>']

    # one subtle region per department (its subnet)
    for d, gx, gw in groups:
        hot = st["current"] in {d["switch"], *d["devices"]}
        out.append(f'<rect x="{gx:.1f}" y="{GROUP_Y}" width="{gw}" height="{GROUP_H}" rx="10" '
                   f'fill="#f8fafc" stroke="{"#93c5fd" if hot else "#e2e8f0"}" '
                   f'stroke-width="{2 if hot else 1}"/>')
        out.append(f'<text x="{gx + 12:.1f}" y="{GROUP_Y + 18}" font-size="10" font-weight="700" '
                   f'letter-spacing="0.8" fill="{GRAY}">{_esc(_clip(d["name"].upper(), 18))} SUBNET</text>')

    for color, w, dash, links in layers:
        for a, b in links:
            out.append(f'<path d="{_edge_path(pos, a, b)}" fill="none" stroke="{color}" '
                       f'stroke-width="{w}" stroke-linejoin="round" '
                       + (f'stroke-dasharray="{dash}" ' if dash else "") + '/>')

    def style(name):
        stroke, fill, w, dash, text = "#cbd5e1", "#ffffff", 1.2, "", NAVY
        if name in st["done"]:
            stroke, fill, w = TEAL, "#f0fdfa", 2
        if name == st["last_ok"]:
            fill = "#ccfbf1"
        if name in disabled:
            stroke, fill, dash, text = RED, "#f1f5f9", "4 3", "#94a3b8"
        if name == st["next"]:
            stroke, w, dash = BLUE, 2, "5 4"
        if name == st["current"]:
            stroke, fill, w, dash = BLUE, "#eff6ff", 3, ""
        if name == st["failed"]:
            stroke, fill, w, dash = RED, "#fef2f2", 3, ""
        return stroke, fill, w, dash, text

    def card(name, w, h):
        cx, top, _ = pos[name]
        stroke, fill, sw, dash, text = style(name)
        x = cx - w / 2
        rect = (f'<rect x="{x:.1f}" y="{top}" width="{w}" height="{h}" rx="8" fill="{fill}" '
                f'stroke="{stroke}" stroke-width="{sw}" filter="url(#sh)" '
                + (f'stroke-dasharray="{dash}" ' if dash else "") + '/>')
        return x, top, text, stroke, rect

    def down_tag(name, w, top):
        if name in disabled:
            return (f'<text x="{pos[name][0] + w / 2 - 6:.1f}" y="{top + 12}" font-size="8" '
                    f'font-weight="700" text-anchor="end" fill="{RED}">DOWN</text>')
        return ""

    # router
    x, top, text, stroke, rect = card(router, RT_W, RT_H)
    out.append(f'<g><title>{_esc(router)}</title>{rect}')
    out.append(_icon("router", x + 14, top + 22, 34, RED if stroke == RED else BLUE))
    out.append(f'<text x="{x + 60:.1f}" y="{top + 32}" font-size="16" font-weight="700" fill="{text}">Router</text>')
    out.append(f'<text x="{x + 60:.1f}" y="{top + 49}" font-size="11" fill="{GRAY}">'
               f'Gateway for {len(topo["departments"])} subnets</text>')
    out.append(f'<text x="{x + 60:.1f}" y="{top + 65}" font-size="10.5" fill="{GRAY}">'
               f'Gateway between subnets</text>')
    out.append(down_tag(router, RT_W, top) + "</g>")

    # switches and PCs
    for d in topo["departments"]:
        sw = d["switch"]
        x, top, text, stroke, rect = card(sw, SW_W, SW_H)
        out.append(f'<g><title>{_esc(sw)}</title>{rect}')
        out.append(_icon("switch", x + 12, top + 28, 28, RED if stroke == RED else TEAL))
        tx = x + 50
        out.append(f'<text x="{tx:.1f}" y="{top + 23}" font-size="13" font-weight="700" fill="{text}">{_esc(_clip(d["name"], 14))}</text>')
        out.append(f'<text x="{tx:.1f}" y="{top + 39}" font-size="10.5" fill="{GRAY}">Network Switch</text>')
        out.append(f'<text x="{tx:.1f}" y="{top + 57}" font-size="11.5" font-family="Consolas, monospace" fill="{BLUE}">{_esc(d["network"].network_address)}{_esc(d["cidr"])}</text>')
        out.append(f'<text x="{tx:.1f}" y="{top + 73}" font-size="10.5" fill="{GRAY}">{d["capacity"]} usable hosts</text>')
        out.append(down_tag(sw, SW_W, top) + "</g>")
        for name in d["devices"]:
            x, top, text, stroke, rect = card(name, PC_W, PC_H)
            cx = pos[name][0]
            out.append(f'<g><title>{_esc(name)}</title>{rect}')
            out.append(_icon("pc", cx - 11, top + 9, 22, RED if stroke == RED else NAVY, 1.8))
            out.append(f'<text x="{cx:.1f}" y="{top + 47}" font-size="10.5" font-weight="700" text-anchor="middle" fill="{text}">{_esc(_clip(name, 12))}</text>')
            out.append(f'<text x="{cx:.1f}" y="{top + 62}" font-size="9.5" font-family="Consolas, monospace" text-anchor="middle" fill="{GRAY}">{_esc(devices[name]["ip"])}</text>')
            out.append(down_tag(name, PC_W, top) + "</g>")
        if d["hidden"]:                    # requested hosts that are not simulated
            cx, top, _ = pos[_more_key(d)]
            lo, hi = d["hidden_range"]
            tip = (f'{d["name"]}: {d["hidden"]} more requested hosts ({lo} - {hi}) '
                   f'are counted in the subnet but not drawn or simulated.')
            out.append(f'<g><title>{_esc(tip)}</title>'
                       f'<rect x="{cx - PC_W / 2:.1f}" y="{top}" width="{PC_W}" height="{PC_H}" rx="8" '
                       f'fill="#f8fafc" stroke="#cbd5e1" stroke-width="1.2" stroke-dasharray="4 3"/>')
            more = f'+{d["hidden"]} more'
            fit = ' textLength="80" lengthAdjust="spacingAndGlyphs"' if len(more) > 9 else ""
            out.append(f'<text x="{cx:.1f}" y="{top + 30}" font-size="13" font-weight="700" text-anchor="middle"{fit} fill="{NAVY}">{more}</text>')
            out.append(f'<text x="{cx:.1f}" y="{top + 47}" font-size="9.5" text-anchor="middle" fill="{GRAY}">requested hosts</text>')
            out.append(f'<text x="{cx:.1f}" y="{top + 61}" font-size="9.5" text-anchor="middle" fill="{GRAY}">not simulated</text></g>')

    # the packet: a dot on the link, right next to the current node
    cur = st["current"]
    if cur:
        cx, top, bottom = pos[cur]
        other = st["prev"] or st["next"]
        below = other is not None and pos[other][1] > top
        dy = bottom + 13 if below else top - 13
        out.append(f'<circle cx="{cx:.1f}" cy="{dy:.1f}" r="8" fill="{BLUE}" stroke="#fff" stroke-width="2.5"/>'
                   f'<circle cx="{cx:.1f}" cy="{dy:.1f}" r="2.6" fill="#fff"/>')
    out.append("</svg>")
    return "".join(out)


# --------------------------------------------------------------- status panel
def _kind(topo, name):
    if name == topo["router"]:
        return "router"
    return "switch" if name in {d["switch"] for d in topo["departments"]} else "pc"


def _next_label(packet, hop):
    """Text for 'Next' in an animation frame. At the end of the path the packet
    has only reached its destination if it was actually delivered."""
    path = packet["path"]
    if hop + 1 < len(path):
        return path[hop + 1]
    if packet["status"] == "DELIVERED":
        return "Destination reached"
    return "None - packet cannot be delivered"


def _panel(topo, disabled, packet, hop, final):
    devices = topo["devices"]
    o = ['<div class="panel">',
         f'<div class="ptitle">{_i("send", 15, BLUE)}<span>PACKET SIMULATION</span></div>']

    if not packet:
        o.append('<div class="pill idle">IDLE</div>')
        o.append('<p class="hint">Choose a source and a destination, then press '
                 '<b>SEND PACKET</b>. The packet will travel along the highlighted links.</p>')
        if disabled:
            o.append('<div class="lbl">Devices down</div><div class="val">'
                     + _esc(", ".join(disabled)) + '</div>')
        o.append("</div>")
        return "".join(o)

    path, reached = packet["path"], packet["reached"]
    if final:
        ok = packet["status"] == "DELIVERED"
        o.append(f'<div class="pill {"ok" if ok else "bad"}">'
                 f'{_i("ok" if ok else "fail", 15, "currentColor")}{packet["status"]}</div>')
    else:
        o.append('<div class="pill run">IN TRANSIT</div>')

    dst = next((n for n, d in devices.items() if d["ip"] == packet["dest_ip"]), None)
    o.append(f'<div class="lbl">Source</div><div class="val">{_esc(packet["source"])}'
             f'<span class="ip">{_esc(packet["source_ip"])}</span></div>')
    o.append(f'<div class="lbl">Destination</div><div class="val">{_esc(dst or "Custom IP")}'
             f'<span class="ip">{_esc(packet["dest_ip"] or "-")}</span></div>')

    total = len(path) - 1
    if not final:
        nxt = _next_label(packet, hop)
        o.append(f'<div class="hop"><div class="lbl">Packet hop</div>'
                 f'<div class="big">Hop {hop} of {total}</div>'
                 f'<div class="row"><span>Current</span><b>{_esc(reached[hop])}</b></div>'
                 f'<div class="row"><span>Next</span><b>{_esc(nxt)}</b></div></div>')
    elif packet["status"] == "DELIVERED":
        o.append(f'<div class="lbl">Total hops</div><div class="val">{total}</div>')
    else:
        o.append(f'<div class="reason">{_i("alert", 15, RED)}<div>'
                 f'<b>Reason</b><br>{_esc(packet["reason"])}</div></div>')
        if packet["failed_at"]:
            o.append(f'<div class="lbl">Packet stopped at</div><div class="val">'
                     f'{_esc(packet["failed_at"])}</div>')

    title = "Route travelled" if final and packet["status"] == "FAILED" else "Route"
    o.append(f'<div class="lbl">{title}</div><div class="route">')
    for idx, node in enumerate(path):
        state = "done" if idx < (len(reached) if final else hop) else "todo"
        if not final and idx == hop:
            state = "now"
        if final and node == packet["failed_at"]:
            state = "fail"
        color = {"done": TEAL, "now": BLUE, "fail": RED, "todo": "#94a3b8"}[state]
        if idx:
            o.append(f'<div class="arrow">{_i("down", 12, "#94a3b8")}</div>')
        o.append(f'<div class="node {state}">{_i(_kind(topo, node), 15, color)}'
                 f'<span>{_esc(node)}</span></div>')
    o.append("</div></div>")
    return "".join(o)


CSS = """
body{margin:0;font-family:'Segoe UI',Helvetica,Arial,sans-serif;color:#0f2942;background:transparent}
.wrap{display:flex;gap:16px;align-items:flex-start;flex-wrap:wrap}
.diagram{flex:1 1 520px;min-width:0;background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:12px}
.panel{flex:0 0 250px;box-sizing:border-box;background:#fff;border:1px solid #e2e8f0;border-radius:10px;
 padding:14px;box-shadow:0 1px 3px rgba(15,41,66,.08)}
.ptitle{display:flex;align-items:center;gap:8px;font-size:11px;font-weight:700;letter-spacing:.09em;color:#64748b;margin-bottom:10px}
.pill{display:inline-flex;align-items:center;gap:6px;font-weight:700;font-size:13px;padding:5px 12px;border-radius:6px;margin-bottom:6px;letter-spacing:.04em}
.pill.idle{background:#f1f5f9;color:#64748b}.pill.run{background:#dbeafe;color:#1d4ed8}
.pill.ok{background:#ccfbf1;color:#0f766e}.pill.bad{background:#fee2e2;color:#b91c1c}
.lbl{font-size:10px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#64748b;margin:10px 0 2px}
.val{font-size:14px;font-weight:600}.ip{display:block;font:12px Consolas,monospace;color:#2563eb;font-weight:400}
.hint{font-size:12.5px;color:#475569;line-height:1.45}
.hop{background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:8px 10px;margin-top:10px}
.hop .lbl{margin-top:0}.big{font-size:16px;font-weight:700;color:#1d4ed8;margin-bottom:4px}
.row{display:flex;justify-content:space-between;font-size:12.5px;padding:1px 0}.row span{color:#64748b}
.reason{display:flex;gap:8px;background:#fef2f2;border:1px solid #fecaca;color:#7f1d1d;border-radius:8px;
 padding:8px 10px;margin-top:10px;font-size:12.5px;line-height:1.4}.reason svg{flex:none;margin-top:1px}
.route{display:flex;flex-direction:column;align-items:flex-start}
.arrow{margin-left:8px;line-height:0;padding:1px 0}
.node{display:flex;align-items:center;gap:8px;font-size:12.5px;padding:3px 8px;border-radius:6px;border:1px solid transparent}
.node.done{color:#0f766e;background:#f0fdfa;border-color:#99f6e4}
.node.now{color:#1d4ed8;background:#eff6ff;border-color:#93c5fd;font-weight:700}
.node.fail{color:#b91c1c;background:#fef2f2;border-color:#fca5a5;font-weight:700}
.node.todo{color:#94a3b8}
"""


def topology_html(topo, disabled=(), packet=None, hop=0, final=False, panel=True):
    """Complete HTML for the diagram, optionally with the status panel beside it.

    packet is the dict from send_packet(); hop is the animation step (index into
    packet["reached"]); final=True draws the finished result.
    """
    st = _state(packet, hop, final)
    body = f'<div class="diagram">{_svg(topo, disabled, st)}</div>'
    if panel:
        body += _panel(topo, list(disabled), packet, hop, final)
    return f'<style>{CSS}</style><div class="wrap">{body}</div>'


def view_height(panel=True):
    """Iframe height that fits the diagram (and a 5-node route in the panel)."""
    return 580 if panel else SVG_H + 40


# ---------------------------------------------------------------- self-test
if __name__ == "__main__":
    from subnet import design_vlsm

    r = design_vlsm("192.168.1.0/24",
                    [("CSE", 3), ("AI/ML", 2), ("ECE", 1), ("Admin", 2)])
    topo = build_topology(r["subnets"])
    counts = {d["name"]: len(d["devices"]) for d in topo["departments"]}
    assert counts == {"CSE": 3, "AI/ML": 2, "ECE": 1, "Admin": 2}, counts
    assert len(topo["devices"]) == 8
    for n, d in topo["devices"].items():
        print(n, d["ip"])
    assert topo["devices"]["CSE-PC1"]["ip"] == "192.168.1.1"
    assert topo["devices"]["CSE-PC3"]["ip"] == "192.168.1.3"
    for sub in r["subnets"]:                     # never the network / broadcast address
        for n in next(d for d in topo["departments"] if d["name"] == sub["Department"])["devices"]:
            ip = ipaddress.IPv4Address(topo["devices"][n]["ip"])
            assert ipaddress.IPv4Address(sub["First IP"]) <= ip <= ipaddress.IPv4Address(sub["Last IP"])
            assert topo["devices"][n]["ip"] not in (sub["Network"], sub["Broadcast"])

    same = send_packet(topo, "CSE-PC1", "CSE-PC3")
    assert same["status"] == "DELIVERED" and same["path"] == ["CSE-PC1", "CSE Switch", "CSE-PC3"]
    assert send_packet(topo, "ECE-PC1", "Admin-PC1")["status"] == "DELIVERED"
    diff = send_packet(topo, "CSE-PC1", "AIML-PC2")
    assert diff["path"] == ["CSE-PC1", "CSE Switch", "Router", "AI/ML Switch", "AIML-PC2"]
    assert diff["status"] == "DELIVERED"
    down = send_packet(topo, "CSE-PC1", "AIML-PC2", disabled={"AIML-PC2"})
    assert down["status"] == "FAILED" and down["failed_at"] == "AIML-PC2"
    sw = send_packet(topo, "CSE-PC1", "AIML-PC2", disabled={"Router"})
    assert sw["reached"] == ["CSE-PC1", "CSE Switch"] and sw["failed_at"] == "Router"
    out = send_packet(topo, "CSE-PC1", "8.8.8.8")
    assert out["status"] == "FAILED" and "no route" in out["reason"]
    ghost = send_packet(topo, "CSE-PC1", "192.168.1.6")   # inside CSE /29, no such PC
    assert ghost["status"] == "FAILED" and "no device" in ghost["reason"]
    assert send_packet(topo, "CSE-PC1", "abc")["status"] == "FAILED"
    assert send_packet(topo, "CSE-PC1", topo["devices"]["AIML-PC1"]["ip"])["status"] == "DELIVERED"
    netaddr = send_packet(topo, "CSE-PC1", "192.168.1.8")   # AI/ML network address
    assert netaddr["status"] == "FAILED" and "network address" in netaddr["reason"]
    assert netaddr["failed_at"] == "AI/ML Switch"            # same stopping point as before
    bcast = send_packet(topo, "CSE-PC1", "192.168.1.7")      # CSE broadcast address
    assert bcast["status"] == "FAILED" and "broadcast address" in bcast["reason"]
    assert bcast["path"] == ["CSE-PC1", "CSE Switch"]
    assert "<svg" in topology_html(topo, packet=diff, hop=2)
    assert all(d["hidden"] == 0 for d in topo["departments"])   # small example: all PCs
    assert "not simulated" not in topology_html(topo)

    # animation label: "Destination reached" only for a delivered packet
    def last_frame(p):
        return topology_html(topo, packet=p, hop=len(p["reached"]) - 1)
    assert "Destination reached" in last_frame(diff)
    for p in (ghost, out):                         # no device / no route
        assert p["reached"][-1] == p["failed_at"]
        assert "Destination reached" not in last_frame(p)
        assert "cannot be delivered" in last_frame(p)
    assert "Destination reached" not in last_frame(down)   # disabled destination
    assert "AIML-PC2" in last_frame(down)                  # next is still the down PC

    # large departments: only MAX_PCS slots are drawn / simulated per department
    big = build_topology(design_vlsm("10.0.0.0/16", [("Lab", 1000), ("Office", 100),
                                                     ("Tiny", 4)])["subnets"])
    lab, office, tiny = big["departments"]
    assert len(lab["devices"]) == MAX_PCS - 1 and lab["hidden"] == 1000 - (MAX_PCS - 1)
    assert office["hidden"] == 100 - (MAX_PCS - 1) and tiny["hidden"] == 0
    assert len(tiny["devices"]) == 4 and len(big["devices"]) == 2 * (MAX_PCS - 1) + 4
    assert big["devices"]["Lab-PC1"]["ip"] == "10.0.0.1"
    assert str(lab["hidden_range"][1]) == "10.0.3.232"      # 1000th host
    assert "+997 more" in topology_html(big)
    hid = send_packet(big, "Office-PC1", "10.0.0.100")     # requested but not simulated
    assert hid["status"] == "FAILED" and "not simulated" in hid["reason"]
    spare = send_packet(big, "Office-PC1", "10.0.3.240")   # in Lab /22, beyond 1000 hosts
    assert "no device" in spare["reason"]
    assert send_packet(big, "Office-PC1", "Lab-PC3")["status"] == "DELIVERED"
    huge = build_topology(design_vlsm("10.0.0.0/8", [("A", 5_000_000)])["subnets"])
    assert len(huge["devices"]) == MAX_PCS - 1 and len(topology_html(huge)) < 50_000
    print("Simulation tests passed.")
