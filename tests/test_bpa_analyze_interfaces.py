import runpy
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import textfsm


ROOT = Path(__file__).resolve().parents[1]
FIELDS = ("status", "protocol")


class BpaInterfaceAnalysisTests(unittest.TestCase):
    def run_analysis(self, rows):
        provider = Mock()
        provider.get_fields_as_dict_list.return_value = rows
        provider.publish_status.return_value = {"published": True}
        module = types.ModuleType("devpackage.DataProvider")
        module.DeviceDataProvider = Mock(return_value=provider)
        module.CollectionType = types.SimpleNamespace(PRE="pre")
        package = types.ModuleType("devpackage")
        package.DataProvider = module
        context = {"test": "context"}
        with patch.dict(sys.modules, {"devpackage": package, "devpackage.DataProvider": module}):
            script = runpy.run_path(str(ROOT / "bpa_analyze_interfaces.py"), init_globals={"context": context})
            result = script["main"]()
        module.DeviceDataProvider.assert_called_once_with(context)
        provider.get_fields_as_dict_list.assert_called_once_with("pre", *FIELDS)
        self.assertEqual(result, {"published": True})
        return provider

    def test_analysis_reports_states_without_failing_down_interfaces(self):
        rows = [
            dict(zip(FIELDS, values)) for values in (
                (" Up ", "Up"),
                ("Up", "Up"),
                ("Down", "Down"),
                ("Shutdown", "Down"),
                ("Up", "Down"),
                ("Down", "Up"),
                ("Shutdown", "Up"),
            )
        ]
        provider = self.run_analysis(rows)
        provider.publish_pre_status.assert_called_once_with(
            True, "Interface analysis completed; link states are informational"
        )
        fields = [call.args for call in provider.add_pre_status_field.call_args_list]
        self.assertCountEqual(fields, [
            ("Status/protocol", "Up/Up", "Interface state observed", "Passed"),
            ("Status/protocol", "Down/Down", "Interface state observed", "Passed"),
            ("Status/protocol", "Shutdown/Down", "Interface state observed", "Passed"),
        ])

    def test_only_ignored_states_still_pass(self):
        provider = self.run_analysis([{"status": "Up", "protocol": "Down"}])
        provider.publish_pre_status.assert_called_once_with(
            True, "Interface analysis completed; link states are informational"
        )
        provider.add_pre_status_field.assert_called_once_with(
            "Interface analysis", "OK", "No matching interface states found", "Passed"
        )

    def test_missing_and_invalid_data_fail_without_partial_report(self):
        good = dict(zip(FIELDS, ("Up", "Up")))
        cases = [
            ([], "No interface information"),
            ([None], "not a field dictionary"),
            ([{**good, "protocol": ""}], "missing or invalid fields: protocol"),
            ([{**good, "status": "Unknown"}], "Invalid status/protocol"),
        ]
        for rows, expected in cases:
            with self.subTest(expected=expected):
                provider = self.run_analysis(rows)
                provider.publish_pre_status.assert_called_once_with(False, "Interface analysis failed")
                fields = [call.args for call in provider.add_pre_status_field.call_args_list]
                self.assertTrue(any(expected in field[2] for field in fields))
                self.assertTrue(all(field[0] == "Interface analysis" and field[3] == "Failed"
                                    for field in fields))

    def test_bpa_template_supplies_expected_fields(self):
        template_path = ROOT / "templates" / "bpa_iosxr_show_ipv4_interface_brief.textfsm"
        with template_path.open(encoding="utf-8") as template:
            parser = textfsm.TextFSM(template)
            rows = parser.ParseText((ROOT / "IPv4 interface output.txt").read_text(encoding="utf-8"))
        self.assertEqual(tuple(parser.header), FIELDS)
        self.assertEqual(len(rows), 227)
        provider = self.run_analysis([dict(zip(parser.header, row)) for row in rows])
        self.assertTrue(provider.publish_pre_status.call_args.args[0])

    def test_bpa_template_rejects_malformed_rows(self):
        template_path = ROOT / "templates" / "bpa_iosxr_show_ipv4_interface_brief.textfsm"
        with template_path.open(encoding="utf-8") as template:
            parser = textfsm.TextFSM(template)
            with self.assertRaises(textfsm.TextFSMError):
                parser.ParseText("Interface IP-Address Status Protocol Vrf-Name\n"
                                 "BVI1 unassigned Up Up default\nmalformed row\n")


if __name__ == "__main__":
    unittest.main()
