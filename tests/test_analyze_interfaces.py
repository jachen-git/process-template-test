import csv
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import textfsm

from analyze_interfaces import analyze_interfaces, main, parse_interfaces, render_report


ROOT = Path(__file__).resolve().parents[1]
HEADER = "Interface IP-Address Status Protocol Vrf-Name\n"


class InterfaceAnalysisTests(unittest.TestCase):
    def test_uploaded_capture_is_parsed_completely(self):
        capture = (ROOT / "IPv4 interface output.txt").read_text(encoding="utf-8")
        records = parse_interfaces(capture)
        self.assertEqual(len(records), 227)
        summary = analyze_interfaces(records)["summary"]
        self.assertEqual(
            {key: summary[key] for key in ("up", "down", "shutdown", "inconsistent")},
            {"up": 63, "down": 56, "shutdown": 108, "inconsistent": 0},
        )
        self.assertEqual(records[0], {
            "interface": "BVI200", "ip_address": "24.114.112.84",
            "status": "Shutdown", "protocol": "Down", "vrf": "TEST_SGi",
        })
        self.assertEqual(records[-1]["interface"], "HundredGigE0/5/0/31")
        self.assertIn("**nVSatellite", {record["vrf"] for record in records})
        self.assertIn("Bundle-Ether900.10", {record["interface"] for record in records})

    def test_categories_and_summary(self):
        records = parse_interfaces(
            "RP/0/RP0/CPU0:router#show ipv4 interface brief\n"
            "Sun Nov 15 18:43:58.735 UTC\n\n" + HEADER
            + "Bundle-Ether1.10 10.0.0.1 Up Up default\n"
            "TenGigE0/0/0/0 unassigned Down Down default\n"
            "BVI200 192.0.2.1 Shutdown Down TEST_SGi\n"
            "Loopback0 192.0.2.2 Up Down **nVSatellite\n"
            "RP/0/RP0/CPU0:router#\n"
        )
        report = analyze_interfaces(records)
        self.assertEqual(report["summary"], {
            "total": 4, "up": 1, "down": 1, "shutdown": 1,
            "inconsistent": 1, "unassigned": 1, "up_with_ip": 1,
            "by_vrf": {"**nVSatellite": 1, "TEST_SGi": 1, "default": 2},
        })
        text = render_report(report, "text")
        self.assertIn("TenGigE0/0/0/0", text)
        self.assertIn("Loopback0", text)
        self.assertNotIn("BVI200", text)
        self.assertEqual(json.loads(render_report(report, "json")), report)
        csv_rows = list(csv.DictReader(io.StringIO(render_report(report, "csv"))))
        self.assertEqual(len(csv_rows), 4)
        self.assertEqual(csv_rows[2]["category"], "shutdown")

    def test_up_with_ip_requires_address_and_both_states_up(self):
        records = parse_interfaces(
            HEADER
            + "Bundle-Ether1.10 192.0.2.1 Up Up default\n"
            "Loopback1 192.0.2.2 Up Up TEST_VRF\n"
            "TenGigE0/0/0/0 unassigned Up Up default\n"
            "BVI2 192.0.2.3 Up Down default\n"
            "BVI3 192.0.2.4 Down Up default\n"
            "BVI4 192.0.2.5 Down Down default\n"
            "BVI5 192.0.2.6 Shutdown Down default\n"
        )
        report = analyze_interfaces(records)
        self.assertEqual(report["summary"]["up_with_ip"], 2)
        self.assertEqual(report["summary"]["total"], 7)
        self.assertEqual(report["summary"]["up"], 3)
        self.assertEqual(
            report["up_with_ip_interfaces"],
            report["interfaces"][:2],
        )
        text = render_report(report, "text")
        matching_section = text.split(
            "Interfaces with assigned IPv4 address and Status/Protocol Up/Up:\n"
        )[1].split("\n\n")[0]
        self.assertIn("Bundle-Ether1.10", matching_section)
        self.assertIn("Loopback1", matching_section)
        for record in records[2:]:
            self.assertNotIn(record["interface"], matching_section)
        self.assertEqual(json.loads(render_report(report, "json"))["up_with_ip_interfaces"],
                         report["interfaces"][:2])
        self.assertEqual(len(list(csv.DictReader(io.StringIO(render_report(report, "csv"))))), 7)

    def test_no_up_interfaces_with_ip(self):
        report = analyze_interfaces(parse_interfaces(
            HEADER + "BVI1 unassigned Up Up default\nBVI2 192.0.2.1 Down Down default\n"
        ))
        self.assertEqual(report["summary"]["up_with_ip"], 0)
        self.assertEqual(report["up_with_ip_interfaces"], [])
        self.assertIn(
            "Interfaces with assigned IPv4 address and Status/Protocol Up/Up:\nNone\n",
            render_report(report, "text"),
        )

    def test_invalid_input_is_not_silently_skipped(self):
        cases = [
            "", "not a command capture\n", HEADER,
            HEADER + "BVI1 999.1.1.1 Up Up default\n",
            HEADER + "BVI1 192.0.2.1 Up Up\n",
            HEADER + "BVI1 unassigned Unknown Down default\n",
            HEADER + "BVI1 unassigned Up Up default\nmalformed row\n",
            HEADER + "BVI1 unassigned Up Up default\nBVI1 unassigned Down Down default\n",
        ]
        for capture in cases:
            with self.subTest(capture=capture):
                with self.assertRaises((ValueError, textfsm.TextFSMError)):
                    parse_interfaces(capture)

    def test_cli_writes_json_and_reports_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "capture.txt"
            destination = Path(directory) / "report.json"
            source.write_text(HEADER + "BVI1 unassigned Up Up default\n", encoding="utf-8-sig")
            self.assertEqual(main([str(source), "--format", "json", "--output", str(destination)]), 0)
            self.assertEqual(json.loads(destination.read_text())["summary"]["up"], 1)
            with redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(main([str(source), "--format", "csv"]), 0)
            self.assertIn("BVI1,unassigned,Up,Up,default,up", stdout.getvalue())
            for arguments in ([str(source), "--output", str(source)], [str(source.parent / "missing.txt")]):
                with self.subTest(arguments=arguments):
                    with redirect_stderr(io.StringIO()) as stderr:
                        with self.assertRaises(SystemExit) as exc:
                            main(arguments)
                    self.assertEqual(exc.exception.code, 2)
                    self.assertIn("error:", stderr.getvalue())
            self.assertTrue(source.read_text(encoding="utf-8-sig").startswith(HEADER))


if __name__ == "__main__":
    unittest.main()
