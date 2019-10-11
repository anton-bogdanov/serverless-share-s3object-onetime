# serverless-share-s3object-onetime

This is an AWS-native serverless application that lets you share S3 files as easy as giving a public link, with any expiration date and optional self-destruction after one-time use.

End user is given with an individual link like this: `https://<apigw id>.execute-api.<region>.amazonaws.com/<apigw stage>/file.pdf?hash=9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08&alias=Jane`.

When the user opens the link, the application authenticates the user and returns S3 pre-signed link.

I built this application to use myself, as I often want to share a file with someone.

There are plenty of options to do that of course, but I had several constraints, and there wasn't a solution at the time that could satisfy all:
- Must be secure
- Must be easy to download for the other end, a public accessible link
- Must have configurable expiration date
- Must have an option to expire after one-time use
- Administrator must get notified whenever someone uses the link
- Must be 100% serverless

## Architecture

The application uses several AWS services, including:

- Lambda
- API gateway
- S3
- DynamoDB
- Step Functions
- SNS

The entry point is API Gateway, which supports GET and POST requests.

GET is for generating a S3 pre-signed

POST is for putting items to DynamoDB states table, each item has following attributes:
  * `Hash` (String) : SHA1 hash of `S3Key` + `Alias` + Salt)
  * `S3Key` (String): S3 key
  * `Alias` (String): Individual alias for the client
  * `Expires` (Number): DynamoDB TTL represented as unix time stamp
  * `OneTime` (Boolean): One-Time true/false

### GET data flow

![GET data flow diagram](https://www.lucidchart.com/publicSegments/view/5c2f6070-3f61-4b41-b5b7-40111ca882ca/image.png)

The diagram above illustrates data flow for GET requests.

1. A client requests a file by issuing a GET request to API Gateway: `/{APIGW stage}/{s3_key}?hash={hash}&alias={alias}`
2. API GW calls GET Lambda
3. GET Lambda validates input, authorizes against DynamoDB (match of `s3_key`, `hash`, `alias` and validates expiration)
4. GET Lambda starts execution of GET Step Function (doesn't wait for completion), which
    * Checks if the link is one-time
    * If true, it updates TTL in DynamoDB (`Expires` attribute) to current unix timestamp. The link becomes invalid immediately, and DynamoDB will remove this item from the table within 48 hours. If the operation fails, it retries up to 3 times, and then notifies administrator about failure by SNS and terminates
    * If false, it proceeds to the next step
    * Notifies administrator by SNS that the link has been requested
5. GET Lambda generates S3 pre-signed link with short expiration (Default: 15 minutes) and returns it to API Gateway
6. API Gateway returns the link to the client
7. The client downloads the object directly from S3


### POST data flow

![POST data flow diagram](https://www.lucidchart.com/publicSegments/view/744aaa74-8638-469c-97ff-3e4a5cf0f0c2/image.png)
The diagram above illustrates data flow for POST requests.

1. Administrator issues a POST request to add a file (must already exist in S3) to DynamoDB with one or more aliases
2. API Gateway calls POST Lambda
3. POST Lambda ensures the file is present in S3 (HEAD request)
4. POST Lambda calculates SHA1 hash and starts asynchronous execution of POST Step Function, which
    * Loops over provided map in input
    * Each iteration puts an item to `DynamoDB`
    * At the end of loop, it sends the list of links and execution id to the administrator
5. `POST Lambda` returns execution id of `POST Step Function` to `API Gateway`
6. `API Gateway` returns execution id of `POST Step Function` to the caller

## Prerequisites

- AWS account
- S3 bucket for SAM packages
- IAM user for deployment
- SAM CLI installed

## Deployment

This project contains source code and supporting files for a serverless application that you can deploy with the SAM CLI. It includes the following files and folders.

- `get_s3_presigned_url` - Code for the GET Lambda function.
- `template.yaml` - An AWS SAM template that defines the application's AWS resources.
- `envs` - Environment property files (see `staging.properties.example`)
- `sam-package.sh` - Script that calls `sam package` with environment-specific parameters
- `sam-deploy.sh` - Script that calls `sam deploy` with environment-specific parameters

The AWS resources are defined in the `template.yaml` file in this project. You can update the template to add AWS resources through the same deployment process that updates your application code.

To deploy:
- Copy `envs/staging.properties.example` to `envs/<env_name>.properties` and update values.
- ```sam-package.sh <env_name>``` - transforms SAM template to CloudFormation and uploads code to S3
- ```sam-deploy.sh <env_name>``` - Deploys the stack
