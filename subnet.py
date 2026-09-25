"""subnet.py - VLSM (Variable Length Subnet Mask) engine for SubnetX.

Main entry point: design_vlsm(network_text, departments)
"""
import ipaddress
import math

INSUFFICIENT_MSG = "Insufficient IP address space for the requested departments."


def parse_network(text):
    """Return (IPv4Network, None) or (None, error message)."""
    text = str(text).strip()
    try:
        net = ipaddress.IPv4Network(text, strict=False)
    except (ValueError, TypeError):
        return None, "Invalid network. Use the format 192.168.1.0/24."
    if "/" not in text:                 # a bare address would silently become a /32
        return None, "Enter the network in CIDR format, such as 192.168.1.0/24."
    if net.prefixlen > 30:
        return None, "Network is too small. Use a /30 or shorter prefix (for example, /24)."
    return net, None


def validate_departments(departments):
    """departments: list of (name, hosts). Return a list of error messages."""
    errors = []
    if not departments:
        return ["Add at least one department."]
    seen = set()
    for name, hosts in departments:
        name = str(name).strip()
        if not name:
            errors.append("Department name cannot be empty.")
            continue
        key = name.lower()
        if key in seen:
            errors.append(f"Duplicate department name: {name}.")
        seen.add(key)
        try:
            ok = int(hosts) == float(hosts) and int(hosts) > 0
        except (ValueError, TypeError):
            ok = False
        if not ok:
            errors.append(f"{name}: host count must be a positive whole number.")
    return errors


def prefix_for_hosts(hosts):
    """Smallest prefix that gives `hosts` usable addresses.

    Each subnet needs 2 extra addresses (network + broadcast).
    """
    block_bits = max(2, math.ceil(math.log2(hosts + 2)))  # at least /30
    return 32 - block_bits


def describe_subnet(name, required, subnet):
    """Build one row of the subnet table."""
    usable = subnet.num_addresses - 2
    return {
        "Department": name,
        "Required": required,
        "Allocated": usable,
        "CIDR": f"/{subnet.prefixlen}",
        "Subnet Mask": str(subnet.netmask),
        "Network": str(subnet.network_address),
        "First IP": str(subnet.network_address + 1),
        "Last IP": str(subnet.broadcast_address - 1),
        "Broadcast": str(subnet.broadcast_address),
    }


def design_vlsm(network_text, departments):
    """Run the full VLSM design.

    Returns {"ok": bool, "errors": [...], "subnets": [...], "summary": {...}}.
    """
    errors = []
    net, err = parse_network(network_text)
    if err:
        errors.append(err)
    errors += validate_departments(departments)
    if errors:
        return {"ok": False, "errors": errors, "subnets": [], "summary": {}}

    # 1. Clean the input, 2. sort largest first
    reqs = [(str(n).strip(), int(h)) for n, h in departments]
    reqs.sort(key=lambda d: d[1], reverse=True)

    # 3. Allocate one after another, starting at the network address
    subnets = []
    current = int(net.network_address)
    end = int(net.broadcast_address)
    for name, hosts in reqs:
        prefix = prefix_for_hosts(hosts)
        size = 2 ** (32 - prefix)
        if current % size:                      # align to block boundary
            current += size - current % size
        if current + size - 1 > end:            # must fit in the base network
            return {"ok": False, "errors": [INSUFFICIENT_MSG],
                    "subnets": [], "summary": {}}
        sub = ipaddress.IPv4Network((current, prefix))
        subnets.append(describe_subnet(name, hosts, sub))
        current += size

    total_required = sum(h for _, h in reqs)
    total_allocated = sum(s["Allocated"] for s in subnets)
    used_addresses = sum(2 ** (32 - int(s["CIDR"][1:])) for s in subnets)
    summary = {
        "Base Network": str(net),
        "Number of Departments": len(reqs),
        "Total Required Hosts": total_required,
        "Total Addresses": net.num_addresses,
        "Addresses Used by Subnets": used_addresses,
        "Total Allocated Host Capacity": total_allocated,
        "Unused Host Capacity": total_allocated - total_required,
        "Unallocated Addresses": net.num_addresses - used_addresses,
        "Utilization %": round(100 * total_required / net.num_addresses, 1),
        "Design Status": "Valid",
    }
    return {"ok": True, "errors": [], "subnets": subnets, "summary": summary}


# ---------------------------------------------------------------- self-test
if __name__ == "__main__":
    def show(title, net, depts):
        print(f"\n=== {title} ===")
        r = design_vlsm(net, depts)
        if not r["ok"]:
            print("ERRORS:", r["errors"])
            return r
        for s in r["subnets"]:
            print(f'{s["Department"]:8} req={s["Required"]:4} {s["Network"]}{s["CIDR"]:4} '
                  f'{s["First IP"]} - {s["Last IP"]}  bc={s["Broadcast"]}')
        print(r["summary"])
        return r

    r = show("Normal", "192.168.1.0/24",
             [("CSE", 100), ("AI/ML", 50), ("ECE", 30), ("Admin", 20)])
    got = [(s["Network"], s["CIDR"]) for s in r["subnets"]]
    assert got == [("192.168.1.0", "/25"), ("192.168.1.128", "/26"),
                   ("192.168.1.192", "/27"), ("192.168.1.224", "/27")]

    r = show("Small network", "10.0.0.0/26", [("A", 10), ("B", 5), ("C", 2)])
    assert r["ok"] and [s["CIDR"] for s in r["subnets"]] == ["/28", "/29", "/30"]

    r = show("Unsorted input", "172.16.0.0/22", [("Small", 5), ("Big", 500)])
    assert r["subnets"][0]["Department"] == "Big" and r["subnets"][0]["CIDR"] == "/23"

    r = show("Insufficient", "192.168.1.0/24", [("A", 200), ("B", 100)])
    assert r["errors"] == [INSUFFICIENT_MSG]

    r = show("Invalid IP", "192.168.1.999/24", [("A", 10)])
    assert "Invalid network" in r["errors"][0]

    r = show("Missing CIDR", "192.168.1.0", [("A", 10)])
    assert "CIDR format" in r["errors"][0]
    r = show("Too small", "10.0.0.0/31", [("A", 1)])
    assert "/30 or shorter prefix" in r["errors"][0]
    assert show("Smallest allowed", "10.0.0.0/30", [("A", 2)])["ok"]

    r = show("Bad hosts", "192.168.1.0/24", [("A", 0), ("B", -10), ("C", "abc")])
    assert len(r["errors"]) == 3

    r = show("Duplicate", "192.168.1.0/24", [("CSE", 10), ("cse", 20)])
    assert "Duplicate" in r["errors"][0]

    r = show("Exact fit", "192.168.1.0/24", [("A", 126), ("B", 126)])
    assert r["ok"]
    r = show("One too many", "192.168.1.0/24", [("A", 126), ("B", 126), ("C", 1)])
    assert not r["ok"]

    print("\nAll tests passed.")
