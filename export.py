"""export.py - CSV and JSON export for SubnetX."""
import json

import pandas as pd


def to_csv(subnets):
    """Subnet table as CSV text."""
    return pd.DataFrame(subnets).to_csv(index=False)


def to_json(result):
    """Whole network design (summary + subnet table) as JSON text."""
    design = {
        "base_network": result["summary"]["Base Network"],
        "summary": result["summary"],
        "subnets": result["subnets"],
    }
    return json.dumps(design, indent=2)


if __name__ == "__main__":
    from subnet import design_vlsm

    r = design_vlsm("192.168.1.0/24", [("CSE", 100), ("AI/ML", 50)])
    print(to_csv(r["subnets"]))
    data = json.loads(to_json(r))
    assert data["base_network"] == "192.168.1.0/24" and len(data["subnets"]) == 2
    print("Export tests passed.")
