"""BPA pre-check for IOS XR show ipv4 interface brief."""

import devpackage.DataProvider as DeviceDataProvider


dp = DeviceDataProvider.DeviceDataProvider(context)
ctype = DeviceDataProvider.CollectionType
FIELDS = ("status", "protocol")


def main(*args):
    dp.job_execution_log("Analyzing show ipv4 interface brief")
    rows = dp.get_fields_as_dict_list(ctype.PRE, *FIELDS)
    errors = []
    states = set()

    if not rows:
        errors.append("No interface information found in output")
    else:
        for index, row in enumerate(rows, 1):
            if not isinstance(row, dict):
                errors.append("Row {} is not a field dictionary".format(index))
                continue
            missing = [
                field for field in FIELDS
                if not isinstance(row.get(field), str) or not row[field].strip()
            ]
            if missing:
                errors.append("Row {} has missing or invalid fields: {}".format(
                    index, ", ".join(missing)
                ))
                continue
            status, protocol = (row[field].strip() for field in FIELDS)
            if status not in ("Up", "Down", "Shutdown") or protocol not in ("Up", "Down"):
                errors.append("Invalid status/protocol in row {}: {}/{}".format(
                    index, status, protocol
                ))
                continue
            state = (status, protocol)
            if state in (("Up", "Up"), ("Down", "Down"), ("Shutdown", "Down")):
                states.add(state)

    if errors:
        for error in errors:
            dp.add_pre_status_field("Interface analysis", "NOK", error, "Failed")
        dp.publish_pre_status(False, "Interface analysis failed")
        return dp.publish_status()

    for status, protocol in sorted(states):
        dp.add_pre_status_field(
            "Status/protocol", "{}/{}".format(status, protocol),
            "Interface state observed", "Passed",
        )
    if not states:
        dp.add_pre_status_field(
            "Interface analysis", "OK", "No matching interface states found", "Passed"
        )
    dp.publish_pre_status(True, "Interface analysis completed; link states are informational")
    return dp.publish_status()
