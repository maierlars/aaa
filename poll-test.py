from client import *
from http.client import HTTPConnection, HTTPSConnection

def poll(client):
    index = 0
    while True:
        resp = client.agentPoll(index + 1)
        log = resp['result']['log']
        for e in log:
            print(e)
            index = e['index']


options = {"host": "debian:4001"}


conn = HTTPConnection(**options)
client = ArangoClient(conn, None)
poll(client)
