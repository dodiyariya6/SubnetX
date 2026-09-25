"""app.py - SubnetX Streamlit GUI.  Run with:  streamlit run app.py"""
import time

import pandas as pd
import streamlit as st

from export import to_csv, to_json
from simulation import (CUSTOM_IP, MAX_PCS, all_node_names, build_topology,
                        send_packet, topology_html, view_height)
from subnet import design_vlsm

st.set_page_config(page_title="SubnetX", page_icon=":material/lan:", layout="wide")

DEFAULT_DEPARTMENTS = [("CSE", 3), ("AI/ML", 2), ("ECE", 1), ("Admin", 2)]
STEP_DELAY = 0.7   # seconds between packet animation steps
TABLE_COLUMNS = ["Department", "Required", "Allocated", "CIDR", "Subnet Mask",
                 "Network", "First IP", "Last IP", "Broadcast"]



def show_html(container, html, height):
    """Show an HTML page (the diagram) in an iframe."""
    if hasattr(st, "iframe"):
        container.iframe(html, height=height)
    else:                                  # older Streamlit versions
        import streamlit.components.v1 as components
        with container:
            components.html(html, height=height, scrolling=True)


# ------------------------------------------------------------ session state
if "count" not in st.session_state:
    st.session_state.count = len(DEFAULT_DEPARTMENTS)
    for i, (name, hosts) in enumerate(DEFAULT_DEPARTMENTS):
        st.session_state[f"name_{i}"] = name
        st.session_state[f"hosts_{i}"] = hosts
if "result" not in st.session_state:
    st.session_state.result = None
    st.session_state.design_input = None     # inputs the current result was made from
    st.session_state.last_packet = None      # latest packet result, kept across reruns


def current_input(network_text):
    """The design inputs as they are now (used to detect an out-of-date result)."""
    return (network_text.strip(),
            tuple((str(st.session_state[f"name_{i}"]).strip(), st.session_state[f"hosts_{i}"])
                  for i in range(st.session_state.count)))


def add_department():
    i = st.session_state.count
    st.session_state[f"name_{i}"] = ""
    st.session_state[f"hosts_{i}"] = 10
    st.session_state.count += 1


def remove_department():
    if st.session_state.count > 1:
        st.session_state.count -= 1


# ------------------------------------------------------------------ header
st.title("SubnetX")
st.subheader("Automatic Network Designer")
st.write("Enter a base network and the number of hosts each department needs. "
         "SubnetX divides the network into subnets using VLSM and shows the "
         "complete address plan.")
st.divider()

# ------------------------------------------------------------------- input
st.header("1. Design Network")
network_text = st.text_input("Network Address", value="192.168.1.0/24")

st.write("**Departments**")
head_a, head_b = st.columns([3, 2])
head_a.caption("Department")
head_b.caption("Hosts")
for i in range(st.session_state.count):
    col_a, col_b = st.columns([3, 2])
    col_a.text_input("Department", key=f"name_{i}", label_visibility="collapsed",
                     placeholder="Department name")
    col_b.number_input("Hosts", key=f"hosts_{i}", min_value=1, step=1,
                       label_visibility="collapsed")

b1, b2, b3, _ = st.columns([1.2, 1.4, 1.4, 4])
b1.button("Add Department", on_click=add_department)
b2.button("Remove Department", on_click=remove_department)
design_clicked = b3.button("DESIGN NETWORK", type="primary")

# ------------------------------------------------------------ run the design
if design_clicked:
    departments = [(st.session_state[f"name_{i}"], st.session_state[f"hosts_{i}"])
                   for i in range(st.session_state.count)]
    st.session_state.result = design_vlsm(network_text, departments)
    st.session_state.design_input = current_input(network_text)
    # a new design invalidates the old simulation choices and packet result
    st.session_state.last_packet = None
    for key in ("sim_src", "sim_dst", "sim_custom_ip", "disabled_nodes"):
        st.session_state.pop(key, None)

# ----------------------------------------------------------------- results
result = st.session_state.result
stale = result is not None and st.session_state.design_input != current_input(network_text)
if result is not None:
    st.divider()
    if stale:
        st.warning("Design changed — run DESIGN NETWORK again to update the results. "
                   "The results below are for the previous input.",
                   icon=":material/sync_problem:")
    if not result["ok"]:
        for message in result["errors"]:
            st.error(message)
    else:
        summary = result["summary"]

        st.header("2. Network Summary")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Base Network", summary["Base Network"])
        c2.metric("Departments", summary["Number of Departments"])
        c3.metric("Total Required Hosts", summary["Total Required Hosts"])
        c4.metric("Design Status", summary["Design Status"])

        st.header("3. Subnet Allocation")
        table = pd.DataFrame(result["subnets"])[TABLE_COLUMNS]
        st.dataframe(table, hide_index=True, width="stretch")
        e1, e2, _ = st.columns([1, 1, 4])
        e1.download_button("Export CSV", to_csv(result["subnets"]),
                           file_name="subnetx_design.csv", mime="text/csv")
        e2.download_button("Export JSON", to_json(result),
                           file_name="subnetx_design.json", mime="application/json")

        st.header("4. Address Usage")
        u1, u2, u3, u4 = st.columns(4)
        u1.metric("Total Addresses", summary["Total Addresses"])
        u2.metric("Allocated Host Capacity", summary["Total Allocated Host Capacity"])
        u3.metric("Unused Host Capacity", summary["Unused Host Capacity"])
        u4.metric("Host Utilization", f'{summary["Utilization %"]}%',
                  help="Total required hosts ÷ total addresses in the base network.")
        n = summary["Number of Departments"]
        st.caption(f'**Host Utilization** = {summary["Total Required Hosts"]} required hosts ÷ '
                   f'{summary["Total Addresses"]} base-network addresses = '
                   f'{summary["Utilization %"]}% of base-network addresses.')
        st.caption(f'Addresses used by subnets: {summary["Addresses Used by Subnets"]} = '
                   f'{summary["Total Allocated Host Capacity"]} usable host addresses + {2 * n} '
                   f'reserved ({n} network + {n} broadcast addresses: every subnet reserves '
                   f'its first address as the network address and its last as the broadcast '
                   f'address)  |  Unallocated addresses: {summary["Unallocated Addresses"]}')

        # ------------------------------------------- diagram and simulation
        topo = build_topology(result["subnets"])
        st.header(":material/lan: 5. Network Diagram & Packet Simulation")
        st.caption(f"Each department shows its requested hosts as PCs with their assigned "
                   f"IP addresses, up to {MAX_PCS} per department. Larger departments show "
                   f"the first {MAX_PCS - 1} hosts and a \"+N more\" card: those hosts are "
                   f"counted in the subnet table but are not drawn or simulated. The usable "
                   f"capacity of each subnet is written on its switch.")
        st.info("**Logical Network Simulation**  \n"
                "The router connects different subnets, and PCs are assigned IP addresses "
                "from their respective subnet ranges. Packet movement is simulated logically "
                "through the network.", icon=":material/info:")

        st.write("Choose a source and a destination, then send a packet and watch it "
                 "travel through the network. Only the PCs shown in the diagram can send "
                 "or receive.")
        names = list(topo["devices"])
        src_dept = lambda n: topo["devices"][n]["dept"]
        other = next((n for n in names if src_dept(n) is not src_dept(names[0])),
                     names[1] if len(names) > 1 else names[0])
        label = lambda n: n if n == CUSTOM_IP else f'{n} — {topo["devices"][n]["ip"]}'

        with st.container(border=True):
            s1, s2 = st.columns(2)
            src = s1.selectbox("Source", names, key="sim_src", format_func=label)
            dst_choice = s2.selectbox("Destination", names + [CUSTOM_IP],
                                      index=names.index(other), key="sim_dst",
                                      format_func=label)
            dst = dst_choice
            if dst_choice == CUSTOM_IP:
                dst = st.text_input("Destination IP", value="8.8.8.8",
                                    key="sim_custom_ip")
            st.markdown("**:material/report: Fault injection**")
            disabled = st.multiselect(
                "Select devices to disable", all_node_names(topo),
                key="disabled_nodes",
                help="Disable a device to observe how packet delivery is affected.")
            st.caption("Disable a device to observe how packet delivery is affected.")
            send_clicked = st.button("SEND PACKET", type="primary",
                                     icon=":material/send:", disabled=stale,
                                     help="Run DESIGN NETWORK again first." if stale else None)
            st.caption(":material/info: This is a logical educational simulation. "
                       "No real network traffic is sent.")

        own_ip = dst_choice == CUSTOM_IP and str(dst).strip() == topo["devices"][src]["ip"]
        if send_clicked and own_ip:
            st.warning(f"{str(dst).strip()} is the IP address of the source device {src} "
                       f"itself. Choose a different destination.")
            send_clicked = False
        elif send_clicked and dst == src:
            st.warning("Source and destination are the same device.")
            send_clicked = False

        last = st.session_state.last_packet
        if last and not send_clicked:
            p = last["packet"]
            st.caption(f'Showing the last packet sent: {p["source"]} → '
                       f'{last["destination"]}. Press SEND PACKET to send a new one.')
        view = st.container()
        if send_clicked:
            packet = send_packet(topo, src, dst, disabled)
            st.session_state.last_packet = {
                "packet": packet, "disabled": list(disabled),
                "destination": dst if dst_choice != CUSTOM_IP else str(dst).strip() or "-"}
            slot = view.empty()
            # move the packet one node at a time
            for hop in range(len(packet["reached"])):
                show_html(slot, topology_html(topo, disabled, packet, hop=hop),
                          view_height())
                time.sleep(STEP_DELAY)
            show_html(slot, topology_html(topo, disabled, packet, final=True),
                      view_height())
        elif last:                         # keep the latest result across reruns
            show_html(view, topology_html(topo, last["disabled"], last["packet"],
                                          final=True), view_height())
        else:
            show_html(view, topology_html(topo, disabled), view_height())
