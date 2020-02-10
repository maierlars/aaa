#!/bin/bash
set -o pipefail

ME=$(realpath $0)
SCRIPTDIR=$(dirname $ME)

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
USEEA=0

while [ "$1" != "" ]; do
  case $1 in
    -n )  shift
          DEPLOYMENTNAMESPACE=$1
          ;;
    -ea ) USEEA=1
          ;;
    --dump ) shift
          DUMPPREFIX=$1
          ;;
    * )
        if [ -n "$DEPLOYMENTNAME" ] ; then
          echo "Use $0 <deploymentname> [-n <namespace>] [-ea]"
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

EASERVICE=null
if [ "$USEEA" != "0" ] ; then
  EASERVICE=$(kubectl get service -o json -n $DEPLOYMENTNAMESPACE $DEPLOYMENTNAME-ea | jq -r .status.loadBalancer.ingress[0].ip)
fi

JWT=
JWTSECRET=
if [ "$JWTSECRETNAME" != "None" ] ; then
  JWTSECRET=$(kubectl get secret -o json -n $DEPLOYMENTNAMESPACE $JWTSECRETNAME | jq -r .data.token | base64 -d -w0)

  if [ ! $? -eq 0 ] ; then
    echo "Failed to get jwt-secret"
    exit 0
  fi

  JWT=$(jwtgen -a HS256 -s "$JWTSECRET" -c server_id=hans -c iss=arangodb)
  echo $JWT
fi

AGENTPOD=$(kubectl get pods -o json -n $DEPLOYMENTNAMESPACE -l role=agent,arango_deployment=$DEPLOYMENTNAME | jq -r .items[0].metadata.name)
if [ ! $? -eq 0 ] ; then
  echo "Failed to get agency-pod"
  exit 0
fi

MUSTFORWARD=1
HOST=localhost
PORT=9898
SCHEME=https
AAAPARAMS=-k

if [ "$TLSCA" = "None" ] ; then
  echo Using http, no encryption.
  SCHEME=http
  AAAPARAMS=
fi

if [ "$DUMPPREFIX" != "" ] ; then
  AAAPARAMS=$AAAPARAMS --dump=$DUMPPREFIX
fi

if [ "$EASERVICE" != "null" ] ; then
  HOST=$EASERVICE
  PORT=8529
  MUSTFORWARD=0
fi

if [ "$MUSTFORWARD" == "1" ] ; then
  # create pod port-forwarding
  kubectl port-forward -n $DEPLOYMENTNAMESPACE $AGENTPOD 9898:8529 &
  PFPID=$!
  sleep 2
fi

python3 $SCRIPTDIR/aaa.py $AAAPARAMS $SCHEME://$HOST:$PORT/ $JWT

kill -9 $PFPID
