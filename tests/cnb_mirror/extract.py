"""Pull the snapshot stage script and env out of the proposed .cnb.yml exactly as written,
and check the anchor wiring (crontab + web trigger run the same pipeline)."""
import json
import sys

import yaml

cfg = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
btn = yaml.safe_load(open(sys.argv[2], encoding="utf-8"))
cron = cfg["main"]["crontab: 0 */6 * * *"]
assert len(cron) == 2, cron
assert cron[0]["name"] == "mirror-from-github"
snap = cron[1]
assert snap == cfg["main"]["web_trigger_snapshot"][0], "web trigger and crontab differ"
assert cfg["main"]["web_trigger_sync"][0]["name"] == "mirror-from-github"
events = [b["event"] for b in btn["branch"][0]["buttons"]]
assert events == ["web_trigger_sync", "web_trigger_snapshot"], events
open(sys.argv[3], "w", encoding="utf-8").write(snap["stages"][0]["script"])
json.dump(snap["env"], open(sys.argv[4], "w"))
print("pipeline:", snap["name"], "| runner:", snap["runner"], "| lock:", snap["lock"], "| timeout:", snap["stages"][0]["timeout"])
print("env:", snap["env"])
