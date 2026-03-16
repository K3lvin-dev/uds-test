#!/bin/bash
set -e

echo "Initializing LocalStack resources..."

awslocal s3 mb s3://submissions-bucket

awslocal sqs create-queue \
  --queue-name submissions-queue \
  --attributes VisibilityTimeout=120

echo "LocalStack resources created successfully."
