#!/usr/bin/env bash

ENV_NAME_ARG="${1}"

set -e
set -o nounset

ENV_NAME="${ENV_NAME_ARG:=staging}"

source "envs/${ENV_NAME}.properties"

sam deploy --template-file packaged.yaml \
--stack-name "${ENV_NAME}-serverless-share-s3object-onetime" \
--capabilities CAPABILITY_IAM \
--parameter-overrides \
"EnvName=${ENV_NAME}" \
"AdminEmail=${ADMIN_EMAIL}" \
;
