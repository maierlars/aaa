import json
import sys, ssl
from http.client import HTTPConnection, HTTPSConnection

class ArangoError(RuntimeError):
  pass

class ArangoClient:

  def __init__(self, connection, jwt):
    self.connection = connection
    self.jwt = jwt

  class QueryCursor:

    def __init__(self, client, cursor):
      self.client = client
      self.hasMore = cursor["hasMore"]
      self.result = cursor["result"]

      if self.hasMore:
        self.id = cursor["id"]


    def __iter__(self):
      while True:
        for x in self.result:
          yield x
        if not self.hasMore:
          break
        response = self.client.request("PUT", "/_api/cursor/{}".format(self.id))
        if response["error"]:
          ArangoClient.raiseArangoError(response)

        self.hasMore = response["hasMore"]
        self.result = response["result"]

  def request(self, method, url, body = None, header = dict()):
    if not self.jwt == None:
      header["Authorization"] = "bearer " + self.jwt

    self.connection.request(method, url, json.dumps(body), header)
    with self.connection.getresponse() as httpresp:
      return json.load(httpresp)

  def query(self, string, **binds):
    body = { "query": string, "bindVars": binds }

    response = self.request("POST", "/_api/cursor", body)
    ArangoClient.checkArangoError(response)
    return self.QueryCursor(self, response)

  def raiseArangoError(response):
    raise ArangoError("{errorMessage} ({errorNum})".format(**response))

  def checkArangoError(response):
    if response["error"]:
      ArangoClient.raiseArangoError(response)



# options = {"context": ssl._create_unverified_context(), "host": "172.30.0.11:8531"}


# conn = HTTPSConnection(**options)
# client = ArangoClient(conn, jwt)
# cursor = client.query("for l in log return l")
# for l in cursor:
#  print(l)
# cursor = client.query("let x = (for l in log sort l._key limit 1 return l) for s in compact filter s._key >= x._key sort s._key limit 1 return s")
# for l in cursor:
#   print(l)


