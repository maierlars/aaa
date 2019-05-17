import cProfile
import argparse
import json
from agency import *

parser = argparse.ArgumentParser()
parser.add_argument("log", help="log file", type=str)
parser.add_argument('snap', nargs='?', type=str, help="optional, snapshot file")
args = parser.parse_args()

log = None
snap = None

with open(args.log, "r") as f:
    log = json.load(f)

if args.snap:
    with open(args.snap, "r") as f:
        snap = json.load(f)

def apply():
    agency = AgencyStore(snap)

    for l in log:
        agency.apply(l["request"])

cProfile.run("apply()")
