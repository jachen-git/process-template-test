import json
import os
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import parse_iosxr_ipv4_int_brief as parser  # noqa: E402

SAMPLE = os.path.join(ROOT, "samples", "show_ipv4_interface_brief.txt")

LEGACY_OUTPUT = """\
RP/0/0/CPU0:XR#show ipv4 interface brief
Thu Jan  1 00:00:00.000 UTC

Interface                      IP-Address      Status                Protocol
Loopback0                      1.1.1.1         Up                    Up
MgmtEth0/0/CPU0/0              unassigned      Shutdown              Down
GigabitEthernet0/0/0/0         10.0.12.1       Up                    Up
RP/0/0/CPU0:XR#
"""


class ParseTests(unittest.TestCase):
    def setUp(self):
        with open(SAMPLE, encoding="utf-8") as handle:
            self.records = parser.parse_output(handle.read())

    def test_parses_all_rows(self):
        self.assertEqual(len(self.records), 10)
        self.assertEqual(
            self.records[0],
            {
                "interface": "Loopback0",
                "ip_address": "10.0.0.1",
                "status": "Up",
                "protocol": "Up",
                "vrf": "default",
            },
        )
        self.assertEqual(self.records[7]["interface"], "TenGigE0/1/0/0.100")
        self.assertEqual(self.records[7]["vrf"], "CUST_A")

    def test_legacy_output_without_vrf_column(self):
        records = parser.parse_output(LEGACY_OUTPUT)
        self.assertEqual(len(records), 3)
        self.assertEqual(records[1]["status"], "Shutdown")
        self.assertTrue(all(r["vrf"] == "default" for r in records))

    def test_analysis(self):
        summary = parser.analyze(self.records)
        self.assertEqual(summary["total_interfaces"], 10)
        self.assertEqual(summary["with_ip_address"], 7)
        self.assertEqual(summary["unassigned_ip"], 3)
        self.assertEqual(summary["status_counts"], {"Up": 7, "Shutdown": 2, "Down": 1})
        self.assertEqual(summary["vrf_counts"]["CUST_A"], 1)
        self.assertEqual(summary["up_protocol_down"], ["GigabitEthernet0/0/0/1"])
        self.assertEqual(
            summary["admin_shutdown"],
            ["MgmtEth0/RSP1/CPU0/0", "GigabitEthernet0/0/0/2"],
        )
        self.assertEqual(summary["down"], ["TenGigE0/1/0/0.200"])
        self.assertEqual(summary["duplicate_ips"], {})

    def test_duplicate_ip_detection(self):
        records = self.records + [
            {
                "interface": "Loopback1",
                "ip_address": "10.0.0.1",
                "status": "Up",
                "protocol": "Up",
                "vrf": "default",
            }
        ]
        summary = parser.analyze(records)
        self.assertEqual(
            summary["duplicate_ips"], {"10.0.0.1": ["Loopback0", "Loopback1"]}
        )

    def test_cli_json_with_filter(self):
        out = StringIO()
        with redirect_stdout(out):
            rc = parser.main([SAMPLE, "--format", "json", "--vrf", "CUST_A"])
        self.assertEqual(rc, 0)
        data = json.loads(out.getvalue())
        self.assertEqual(len(data["interfaces"]), 1)
        self.assertEqual(data["analysis"]["total_interfaces"], 1)

    def test_cli_csv(self):
        out = StringIO()
        with redirect_stdout(out):
            parser.main([SAMPLE, "--format", "csv", "--status", "shutdown"])
        lines = out.getvalue().strip().splitlines()
        self.assertEqual(lines[0], "interface,ip_address,status,protocol,vrf")
        self.assertEqual(len(lines), 3)


if __name__ == "__main__":
    unittest.main()
