# IPv4 interface status analysis

Parse Cisco IOS XR `show ipv4 interface brief` captures with TextFSM and
analyze interface status using Python 3.10 or newer. The included
`IPv4 interface output.txt` is the example capture.

## Setup

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

On Windows, if PowerShell activation is restricted, use
`.\.venv\Scripts\python.exe` instead of `python` in the commands below.

## Usage

```powershell
python analyze_interfaces.py "IPv4 interface output.txt"
python analyze_interfaces.py "IPv4 interface output.txt" --format json --output report.json
python analyze_interfaces.py "IPv4 interface output.txt" --format csv --output interfaces.csv
```

The text report shows totals, category counts, unassigned addresses, counts per
VRF, and operationally down or inconsistent interfaces. It also counts and lists
interfaces with an assigned IPv4 address and **both Status and Protocol Up**,
including their address and VRF. `unassigned` interfaces do not match.

JSON includes the summary and every parsed interface, with this matching count
in `summary.up_with_ip` and the matching records in `up_with_ip_interfaces`.
CSV continues to include every interface and its category.
Omit `--output` to print to the console.

| Category | Status / Protocol | Meaning |
| --- | --- | --- |
| `up` | Up / Up | Interface and protocol are up |
| `down` | Down / Down | Operationally down; investigate if expected to be active |
| `shutdown` | Shutdown / Down | Administratively disabled; excluded from the attention list |
| `inconsistent` | Any other supported combination | Status and protocol do not agree |

`unassigned` addresses are counted, not treated as faults: interfaces can be
up without an IPv4 address. A down link is not necessarily a failure without
an expected-state baseline. Shutdowns remain visible in JSON/CSV.

The template is in `templates\iosxr_show_ipv4_interface_brief.textfsm`.
Captures must contain the five-column header including `Vrf-Name`; command
prompts and timestamps before the header are accepted. Use one command
capture per input file. Missing/empty tables, malformed rows, invalid IPv4
addresses, duplicate interfaces, and file errors produce an explicit error
and exit code 2 rather than a partial report. Successful analysis exits 0,
even when interfaces are down.

## BPA process template

For BPA, upload `bpa_analyze_interfaces.py` in the Scripts tab and attach it
as a Script rule to a `show ipv4 interface brief` process-template command.
Configure that command's TextFSM processing with
`templates\bpa_iosxr_show_ipv4_interface_brief.textfsm`. Its field names are
case-sensitive: `status` and `protocol`.
The script uses BPA's `devpackage.DataProvider` and the PRE collection; it
does not import `ipaddress`, `collections`, or the standalone Python TextFSM
package.

The pre-check reports each observed Up/Up, Down/Down, or Shutdown/Down state
once, without counts. Other valid status/protocol combinations are ignored.
Link states are informational and do not fail the check. Missing or invalid
fields and an empty result fail the pre-check. It does not retrieve interface
names, addresses, or VRFs. The BPA runtime supplies `context`; the script is
not a standalone command-line program. Configure the parser to reject
malformed rows rather than silently omit them.

## Tests

```powershell
python -m unittest discover -s tests -v
```
