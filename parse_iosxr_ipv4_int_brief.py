#!/usr/bin/env python3
"""Parse Cisco IOS XR ``show ipv4 interface brief`` output with TextFSM.

The raw CLI output is converted into structured data (a list of dicts) and a
short analysis is produced (interface counts per status, per VRF, interfaces
that are admin up but protocol down, duplicate IP addresses, ...).

Examples::

    # Parse a saved CLI capture and print a table + analysis
    python parse_iosxr_ipv4_int_brief.py samples/show_ipv4_interface_brief.txt

    # Emit JSON (structured records + analysis)
    python parse_iosxr_ipv4_int_brief.py capture.txt --format json

    # Emit CSV of the records only
    python parse_iosxr_ipv4_int_brief.py capture.txt --format csv

    # Read from stdin
    cat capture.txt | python parse_iosxr_ipv4_int_brief.py -
"""

import argparse
import csv
import io
import json
import os
import sys
from collections import Counter

import textfsm

DEFAULT_TEMPLATE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "templates",
    "cisco_iosxr_show_ipv4_interface_brief.textfsm",
)

UNASSIGNED = "unassigned"


def parse_output(cli_output, template_path=DEFAULT_TEMPLATE):
    """Parse raw CLI output and return a list of dicts (lower-case keys)."""
    with open(template_path, encoding="utf-8") as template:
        fsm = textfsm.TextFSM(template)
    rows = fsm.ParseText(cli_output)
    headers = [h.lower() for h in fsm.header]
    records = []
    for row in rows:
        record = dict(zip(headers, row))
        if not record.get("vrf"):
            record["vrf"] = "default"
        records.append(record)
    return records


def analyze(records):
    """Return a summary analysis of the parsed records."""
    ip_counter = Counter(
        r["ip_address"] for r in records if r["ip_address"].lower() != UNASSIGNED
    )
    return {
        "total_interfaces": len(records),
        "with_ip_address": sum(
            1 for r in records if r["ip_address"].lower() != UNASSIGNED
        ),
        "unassigned_ip": sum(
            1 for r in records if r["ip_address"].lower() == UNASSIGNED
        ),
        "status_counts": dict(Counter(r["status"] for r in records)),
        "protocol_counts": dict(Counter(r["protocol"] for r in records)),
        "vrf_counts": dict(Counter(r["vrf"] for r in records)),
        "up_up": [
            r["interface"]
            for r in records
            if r["status"].lower() == "up" and r["protocol"].lower() == "up"
        ],
        "admin_shutdown": [
            r["interface"] for r in records if r["status"].lower() == "shutdown"
        ],
        "up_protocol_down": [
            r["interface"]
            for r in records
            if r["status"].lower() == "up" and r["protocol"].lower() != "up"
        ],
        "down": [r["interface"] for r in records if r["status"].lower() == "down"],
        "duplicate_ips": {
            ip: [r["interface"] for r in records if r["ip_address"] == ip]
            for ip, count in ip_counter.items()
            if count > 1
        },
    }


def format_table(records):
    """Render records as a fixed-width text table."""
    headers = ["interface", "ip_address", "status", "protocol", "vrf"]
    widths = {
        h: max([len(h)] + [len(str(r.get(h, ""))) for r in records]) for h in headers
    }
    lines = ["  ".join(h.upper().ljust(widths[h]) for h in headers)]
    lines.append("  ".join("-" * widths[h] for h in headers))
    for r in records:
        lines.append("  ".join(str(r.get(h, "")).ljust(widths[h]) for h in headers))
    return "\n".join(line.rstrip() for line in lines)


def format_analysis(summary):
    """Render the analysis summary as human readable text."""

    def fmt_list(items):
        return ", ".join(items) if items else "none"

    def fmt_counts(counts):
        return ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "none"

    dup = summary["duplicate_ips"]
    dup_text = (
        "; ".join(f"{ip} ({', '.join(ifs)})" for ip, ifs in sorted(dup.items()))
        if dup
        else "none"
    )
    return "\n".join(
        [
            "Analysis",
            "--------",
            f"Total interfaces       : {summary['total_interfaces']}",
            f"With IPv4 address      : {summary['with_ip_address']}",
            f"Unassigned IPv4        : {summary['unassigned_ip']}",
            f"Status counts          : {fmt_counts(summary['status_counts'])}",
            f"Protocol counts        : {fmt_counts(summary['protocol_counts'])}",
            f"VRF counts             : {fmt_counts(summary['vrf_counts'])}",
            f"Up/Up                  : {fmt_list(summary['up_up'])}",
            f"Admin shutdown         : {fmt_list(summary['admin_shutdown'])}",
            f"Up but protocol down   : {fmt_list(summary['up_protocol_down'])}",
            f"Down                   : {fmt_list(summary['down'])}",
            f"Duplicate IPv4 address : {dup_text}",
        ]
    )


def format_csv(records):
    """Render records as CSV text."""
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf, fieldnames=["interface", "ip_address", "status", "protocol", "vrf"]
    )
    writer.writeheader()
    writer.writerows(records)
    return buf.getvalue()


def build_arg_parser():
    parser = argparse.ArgumentParser(
        description="Parse Cisco IOS XR 'show ipv4 interface brief' output "
        "into structured data using TextFSM."
    )
    parser.add_argument(
        "input", help="File containing the CLI output, or '-' to read from stdin"
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["table", "json", "csv"],
        default="table",
        help="Output format (default: table)",
    )
    parser.add_argument(
        "-t",
        "--template",
        default=DEFAULT_TEMPLATE,
        help="Path to the TextFSM template (default: bundled template)",
    )
    parser.add_argument("--vrf", help="Only include interfaces in this VRF")
    parser.add_argument(
        "--status", help="Only include interfaces with this status (e.g. Up, Shutdown)"
    )
    return parser


def main(argv=None):
    args = build_arg_parser().parse_args(argv)

    if args.input == "-":
        cli_output = sys.stdin.read()
    else:
        with open(args.input, encoding="utf-8") as handle:
            cli_output = handle.read()

    try:
        records = parse_output(cli_output, args.template)
    except textfsm.TextFSMError as exc:
        print(f"Failed to parse input: {exc}", file=sys.stderr)
        return 1

    if args.vrf:
        records = [r for r in records if r["vrf"] == args.vrf]
    if args.status:
        records = [r for r in records if r["status"].lower() == args.status.lower()]

    summary = analyze(records)

    if args.format == "json":
        print(json.dumps({"interfaces": records, "analysis": summary}, indent=2))
    elif args.format == "csv":
        sys.stdout.write(format_csv(records))
    else:
        print(format_table(records))
        print()
        print(format_analysis(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
