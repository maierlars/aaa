#!/bin/bash
set -o pipefail

# check if KUBECONFIG is set
if [ -z "$KUBECONFIG" ] ; then
  echo "KUBECONFIG not set"
  exit 0
fi


# check if DEPLOYMENTNAME is set, override it by parameter 1
if [ -n "$1" ] ; then
  DEPLOYMENTNAME=$1
fi

if [ -z "$DEPLOYMENTNAME" ] ; then
  echo "DEPLOYMENTNAME not set"
  echo "Use $0 <deploymentname>"
  exit 0
fi

DEPLOYMENTRES=$(kubectl get arango -o json $DEPLOYMENTNAME)
JWTSECRETNAME=$(echo $DEPLOYMENTRES | jq -r .spec.auth.jwtSecretName)
TLSCA=$(echo $DEPLOYMENTRES | jq -r .spec.tls.caSecretName)


JWTSECRET=$(kubectl get secret -o json $JWTSECRETNAME | jq -r .data.token | base64 -d -w0)

if [ ! $? -eq 0 ] ; then
  echo "Failed to get jwt-secret"
  exit 0
fi

JWT=$(jwtgen -a HS256 -s "$JWTSECRET" -c server_id=hans -c iss=arangodb)
AGENTPOD=$(kubectl get pods -o json -l role=agent -l arango_deployment=$DEPLOYMENTNAME | jq -r .items[0].metadata.name)

if [ ! $? -eq 0 ] ; then
  echo "Failed to get agency-pod"
  exit 0
fi

SCHEME=https
AAAPARAMS=-k

if [ "$TLSCA" = "None" ] ; then
  echo Using http, no encryption.
  SCHEME=http
  AAAPARAMS=
fi

# create pod port-forwarding
kubectl port-forward $AGENTPOD 9898:8529 &
PFPID=$!
sleep 2
python3 aaa.py $AAAPARAMS $SCHEME://localhost:9898/ $JWT

kill -9 $PFPID
