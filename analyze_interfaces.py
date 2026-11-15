"""Parse and analyze Cisco IOS XR 'show ipv4 interface brief' captures."""

import argparse
import csv
import io
import ipaddress
import json
import sys
from collections import Counter
from pathlib import Path

import textfsm


TEMPLATE = Path(__file__).resolve().parent / "templates" / "iosxr_show_ipv4_interface_brief.textfsm"
FIELDS = ("interface", "ip_address", "status", "protocol", "vrf")
CATEGORIES = ("up", "down", "shutdown", "inconsistent")


def parse_interfaces(output: str) -> list[dict[str, str]]:
    """Return all interface rows; reject missing tables and malformed records."""
    with TEMPLATE.open(encoding="utf-8") as template:
        parser = textfsm.TextFSM(template)
        rows = parser.ParseText(output)
    if not rows:
        raise ValueError("No interface rows found; expected IOS XR show ipv4 interface brief output.")

    interfaces = []
    seen = set()
    for row in rows:
        record = dict(zip(FIELDS, row))
        name = record["interface"]
        if name in seen:
            raise ValueError(f"Duplicate interface: {name}")
        seen.add(name)
        if record["ip_address"] != "unassigned":
            try:
                ipaddress.IPv4Address(record["ip_address"])
            except ipaddress.AddressValueError as exc:
                raise ValueError(f"Invalid IPv4 address for {name}: {record['ip_address']}") from exc
        interfaces.append(record)
    return interfaces


def classify_interface(interface: dict[str, str]) -> str:
    """Keep administrative shutdowns distinct from operationally down links."""
    status, protocol = interface["status"], interface["protocol"]
    if status == "Up" and protocol == "Up":
        return "up"
    if status == "Shutdown" and protocol == "Down":
        return "shutdown"
    if status == "Down" and protocol == "Down":
        return "down"
    return "inconsistent"


def analyze_interfaces(interfaces: list[dict[str, str]]) -> dict:
    """Produce a summary and categorized records without assuming intent."""
    records = [
        {**interface, "category": classify_interface(interface)}
        for interface in interfaces
    ]
    counts = Counter(record["category"] for record in records)
    up_with_ip = [
        record for record in records
        if record["ip_address"] != "unassigned" and record["category"] == "up"
    ]
    return {
        "summary": {
            "total": len(records),
            **{category: counts[category] for category in CATEGORIES},
            "unassigned": sum(record["ip_address"] == "unassigned" for record in records),
            "up_with_ip": len(up_with_ip),
            "by_vrf": dict(sorted(Counter(record["vrf"] for record in records).items())),
        },
        "interfaces": records,
        "up_with_ip_interfaces": up_with_ip,
    }


def render_report(report: dict, output_format: str) -> str:
    if output_format == "json":
        return json.dumps(report, indent=2) + "\n"
    if output_format == "csv":
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=(*FIELDS, "category"))
        writer.writeheader()
        writer.writerows(report["interfaces"])
        return stream.getvalue()

    summary = report["summary"]
    lines = [
        f"Total interfaces: {summary['total']}",
        " | ".join(f"{category}: {summary[category]}" for category in CATEGORIES),
        f"Unassigned IPv4 addresses: {summary['unassigned']}",
        f"Interfaces with IPv4 address and Status/Protocol Up/Up: {summary['up_with_ip']}",
        "VRFs: " + ", ".join(f"{vrf}={count}" for vrf, count in summary["by_vrf"].items()),
        "",
        "Interfaces with assigned IPv4 address and Status/Protocol Up/Up:",
    ]
    if not report["up_with_ip_interfaces"]:
        lines.append("None")
    for record in report["up_with_ip_interfaces"]:
        lines.append(
            f"{record['interface']:<32} {record['ip_address']:<15} "
            f"{record['status']}/{record['protocol']}  VRF={record['vrf']}"
        )
    lines.extend(["", "Operationally down or inconsistent interfaces (shutdowns excluded):"])
    attention = [
        record for record in report["interfaces"]
        if record["category"] in ("down", "inconsistent")
    ]
    if not attention:
        lines.append("None")
    for record in attention:
        lines.append(
            f"{record['interface']:<32} {record['ip_address']:<15} "
            f"{record['status']}/{record['protocol']}  "
            f"VRF={record['vrf']}  [{record['category']}]"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="IOS XR show ipv4 interface brief capture")
    parser.add_argument("--format", choices=("text", "json", "csv"), default="text")
    parser.add_argument("--output", type=Path, help="Write the report to a file instead of stdout")
    args = parser.parse_args(argv)
    if args.output and args.input.resolve() == args.output.resolve():
        parser.error("--output must not overwrite the input capture")
    try:
        interfaces = parse_interfaces(args.input.read_text(encoding="utf-8-sig"))
        result = render_report(analyze_interfaces(interfaces), args.format)
        if args.output:
            args.output.write_text(result, encoding="utf-8", newline="")
        else:
            sys.stdout.write(result)
    except (OSError, UnicodeError, ValueError, textfsm.TextFSMError) as exc:
        parser.exit(2, f"error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
