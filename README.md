# process-template-test
Process template test with scripts

## Cisco IOS XR `show ipv4 interface brief` parser

`parse_iosxr_ipv4_int_brief.py` uses the TextFSM template
`templates/cisco_iosxr_show_ipv4_interface_brief.textfsm` to convert the output
of the IOS XR CLI command `show ipv4 interface brief` into structured data
(`interface`, `ip_address`, `status`, `protocol`, `vrf`) and produces a short
analysis (counts per status/protocol/VRF, admin-shutdown interfaces, interfaces
that are up but protocol down, duplicate IPv4 addresses, ...).

Output both with and without the `Vrf-Name` column is supported (the VRF
defaults to `default` when the column is absent).

### Setup

```bash
pip install -r requirements.txt
```

### Usage

```bash
# Table + analysis
python parse_iosxr_ipv4_int_brief.py samples/show_ipv4_interface_brief.txt

# JSON (records + analysis) / CSV (records)
python parse_iosxr_ipv4_int_brief.py samples/show_ipv4_interface_brief.txt --format json
python parse_iosxr_ipv4_int_brief.py samples/show_ipv4_interface_brief.txt --format csv

# Filter by VRF or status, read from stdin
cat capture.txt | python parse_iosxr_ipv4_int_brief.py - --vrf CUST_A --status Up
```

It can also be used as a library:

```python
from parse_iosxr_ipv4_int_brief import parse_output, analyze

records = parse_output(cli_output)
summary = analyze(records)
```

### Tests

```bash
python -m unittest discover -s tests -v
```
