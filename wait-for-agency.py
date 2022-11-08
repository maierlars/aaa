#!/usr/bin/env python3

import psutil
import sys
import time
import requests

def get_cmdline_value(cmdline, key):
    try:
        index = cmdline.index(key)
        return cmdline[index+1]
    except ValueError:
        return None

def wait_for_agency_endpoint():
    # get a list of all current processes
    known = set()

    while True:
        time.sleep(0.5)
        current = set(psutil.pids())
        new = current.difference(known)

        for pid in new:
            p = psutil.Process(pid)
            if p.name() == "arangod" or p.name() == "arangod.exe":
                cmdline = p.cmdline()
                if get_cmdline_value(cmdline, "--agency.activate") == "true":
                    return get_cmdline_value(cmdline, "--agency.my-address")
        known = current

def wait_for_leader(endpoint):
    while True:
        try:
            response = requests.get(f"{endpoint}/_api/agency/config")
            if response.status_code == 200:
                config = response.json()
                if config.get('leaderId'):
                    return config['configuration']['pool'][config['leaderId']]
                else:
                    print("leader not yet available", file=sys.stderr)
            else:
                print(f"status code = {response.status_code}", file=sys.stderr)
        except Exception as e:
            print(f"exception: {e}", file=sys.stderr)
        time.sleep(0.5)


def fix_endpoint_url(url):
    if url.startswith("tcp://"):
        return f"http://{url[6:]}"
    elif url.startswith("ssl://"):
        return f"https://{url[6:]}"
    else:
        return url

def main():
    # wait for the next agency process
    endpoint = wait_for_agency_endpoint()
    endpoint = fix_endpoint_url(endpoint)

    # wait for the agency to have formed
    endpoint = wait_for_leader(endpoint)
    endpoint = fix_endpoint_url(endpoint)

    print(endpoint)



if __name__ == "__main__":
    main()
