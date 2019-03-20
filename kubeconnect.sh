#!/bin/bash
set -o pipefail

# check if KUBECONFIG is set
if [ -z "$KUBECONFIG" ] ; then
  echo "KUBECONFIG not set"
  exit 0
fi

if [ -z "$DEPLOYMENTNAMESPACE" ] ; then
  DEPLOYMENTNAMESPACE=default
fi


DEPLOYMENTNAME=
DUMPPREFIX=

while [ "$1" != "" ]; do
  case $1 in
    -n )  shift
          DEPLOYMENTNAMESPACE=$1
          ;;
    --dump ) shift
          DUMPPREFIX=$1
          ;;
    * )
        if [ -n "$DEPLOYMENTNAME" ] ; then
          echo "Use $0 <deploymentname> [-n <namespace>]"
          exit 1
        fi
        DEPLOYMENTNAME=$1
  esac
  shift
done


if [ -z "$DEPLOYMENTNAMESPACE" ] ; then
  echo "invalid namespace"
  exit 0
fi

echo Using namespace $DEPLOYMENTNAMESPACE

if [ -z "$DEPLOYMENTNAME" ] ; then
  echo "DEPLOYMENTNAME not set"
  exit 0
fi

echo Using deployment $DEPLOYMENTNAME

DEPLOYMENTRES=$(kubectl get arango -o json -n $DEPLOYMENTNAMESPACE $DEPLOYMENTNAME)
JWTSECRETNAME=$(echo $DEPLOYMENTRES | jq -r .spec.auth.jwtSecretName)
TLSCA=$(echo $DEPLOYMENTRES | jq -r .spec.tls.caSecretName)


JWTSECRET=$(kubectl get secret -o json -n $DEPLOYMENTNAMESPACE $JWTSECRETNAME | jq -r .data.token | base64 -d -w0)

if [ ! $? -eq 0 ] ; then
  echo "Failed to get jwt-secret"
  exit 0
fi

JWT=$(jwtgen -a HS256 -s "$JWTSECRET" -c server_id=hans -c iss=arangodb)
AGENTPOD=$(kubectl get pods -o json -n $DEPLOYMENTNAMESPACE -l role=agent,arango_deployment=$DEPLOYMENTNAME | jq -r .items[0].metadata.name)
echo JWT: $JWT

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

if [ "$DUMPPREFIX" != "" ] ; then
  AAAPARAMS=$AAAPARAMS --dump=$DUMPPREFIX

# create pod port-forwarding
kubectl port-forward -n $DEPLOYMENTNAMESPACE $AGENTPOD 9898:8529 &
PFPID=$!
sleep 2

python3 aaa.py $AAAPARAMS $SCHEME://localhost:9898/ $JWT

kill -9 $PFPID
