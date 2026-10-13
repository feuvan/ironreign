#!/usr/bin/env python3
"""Builds the English source string tables.

  Content/Data/Localization/en/Strings.json           every Loc/LocF key + English default in Source/IronReign
  Content/Data/Localization/en/Scenario_<key>.json    scenario display text (names, bios, events...)

Run after changing code text or scenarios, then update the other cultures with the same keys
(check_localization.py lists what is missing).
"""
import sys

from loclib import LOC_DIR, SCENARIO_DIR, load_json, save_json, scan_source_strings, scenario_strings


def main() -> int:
    strings, conflicts = scan_source_strings()
    for message in conflicts:
        print(f"warning: conflicting defaults for {message}", file=sys.stderr)
    save_json(LOC_DIR / "en" / "Strings.json", strings)
    print(f"Strings.json: {len(strings)} keys")
    for path in sorted(SCENARIO_DIR.glob("*.json")):
        scenario = load_json(path)
        table = scenario_strings(scenario)
        save_json(LOC_DIR / "en" / f"Scenario_{scenario.get('key', path.stem)}.json", table)
        print(f"Scenario_{scenario.get('key', path.stem)}.json: {len(table)} keys")
    return 1 if conflicts else 0


if __name__ == "__main__":
    sys.exit(main())
