#!/usr/bin/env bash

ENV_NAME_ARG="${1}"

set -e
set -o nounset

ENV_NAME="${ENV_NAME_ARG:=staging}"

source "envs/${ENV_NAME}.properties"

sam package --template-file template.yaml \
--s3-bucket "${SAM_S3_BUCKET}" \
--output-template-file packaged.yaml
