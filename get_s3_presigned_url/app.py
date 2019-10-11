import json
import urllib.parse
import boto3
from botocore.exceptions import ClientError
import logging
import os
import time
import collections
import re

s3_client = boto3.client('s3')
ddb_client = boto3.client('dynamodb')
sfn_client = boto3.client('stepfunctions')

table_name = os.environ['TABLE_NAME']
log_level = os.environ['LOG_LEVEL']
s3_bucket = os.environ['S3_BUCKET']
state_machine_arn = os.environ['STATE_MACHINE_ARN']

log = logging.getLogger(__name__)
logging.getLogger().setLevel(log_level)

def dynamodb_auth(table_name, input_data):
    epoch_time = str(int(time.time()))
    expression_attr_vals = {
        ":hashvalue":{"S":input_data['hash']},
        ":s3key":{"S":input_data['s3_key']},
        ":epoch_now":{"N":epoch_time}
    }
    log.debug("Expression attributes values dictionary: {0}".format(expression_attr_vals))
    ddb_query = ddb_client.query(
        TableName=table_name,
        ConsistentRead=True,
        # Hash is a reserved keyword, use ExpressionAttributeNames to use #Hash in query
        ExpressionAttributeNames={"#Hash":"Hash"},
        ExpressionAttributeValues=expression_attr_vals,
        KeyConditionExpression="#Hash = :hashvalue AND S3Key = :s3key",
        FilterExpression="Expires > :epoch_now",
        ProjectionExpression="OneTime"
    )
    log.debug("Query response: {0}".format(ddb_query))

    ddb_response = dict()

    if ddb_query.get('Items'):
        log.info("Authorized")
        ddb_response['is_authorized'] = True
        try:
            ddb_response['is_onetime'] = ddb_query.get('Items')[0].get('OneTime').get('BOOL')
        except (AttributeError, IndexError) as e:
            # Consider as one-time, in case the attribute is missing in DynamoDB
            ddb_response['is_onetime'] = True
    else:
        log.info("Unauthorized")
        ddb_response['is_authorized'] = False
    # Save current epoch time for passing to state machine, in one-time case
    # it will set Expires attribute to this TTL, therefore a link won't work anymore
    ddb_response['epoch_now'] = epoch_time

    return ddb_response

def validate_input(input_data):
    regexp = {
      "alias": re.compile('^[A-Za-z0-9]{2,32}$'),
      "hash": re.compile('^[a-f0-9]{64}$'),
      "s3_key": re.compile('[a-zA-Z0-9_./-]{1,1024}$')
    }

    for input, regexp in regexp.items():
        if not regexp.match(input_data[input]):
            log.info("Invalid {0}".format(input))
            return False

    return True

def generate_s3_presigned_url(s3_bucket, s3_key, expires_in=900):
    try:
        response = s3_client.generate_presigned_url('get_object',
                                                    Params={'Bucket': s3_bucket,
                                                            'Key': s3_key},
                                                    ExpiresIn=expires_in)
    except ClientError as e:
        log.error(e)
        return None

    log.info("Successfully generated pre-signed link")
    return response

def lambda_handler(event, context):
    """GET Lambda Handler

    Parameters
    ----------
    event: dict, required
        API Gateway Lambda Proxy Input Format

        Event doc: https://docs.aws.amazon.com/apigateway/latest/developerguide/set-up-lambda-proxy-integrations.html#api-gateway-simple-proxy-for-lambda-input-format

    context: object, required
        Lambda Context runtime methods and attributes

        Context doc: https://docs.aws.amazon.com/lambda/latest/dg/python-context-object.html

    Returns
    ------
    API Gateway Lambda Proxy Output Format: dict

    Return doc: https://docs.aws.amazon.com/apigateway/latest/developerguide/set-up-lambda-proxy-integrations.html
    """

    input_data = {
      "s3_key": urllib.parse.unquote_plus(event['pathParameters']['item']),
      "alias": event['queryStringParameters']['alias'],
      "hash": str(event['queryStringParameters']['hash'])
    }

    if not validate_input(input_data):
        return {
          "statusCode": 400,
          "body": "BAD_REQUEST_PARAMETERS"
        }

    auth_state = dynamodb_auth(table_name, input_data)

    if not auth_state['is_authorized']:
        return {
          "statusCode": 401,
          "body": "UNAUTHORIZED"
        }

    s3_link = generate_s3_presigned_url(s3_bucket, input_data['s3_key'])

    # Merge input_data and auth_state into single dictionary, for passing to Step Function
    state_machine_input = {**input_data, **auth_state}

    # Message body for SNS in case of success
    # Concatenating it here to avoid creating a separate Lambda just for that
    state_machine_input['success_message'] = "Requested 's3://{0}/{1}' by '{2}'. Expired: {3}.".format(
      s3_bucket, input_data['s3_key'], input_data['alias'], auth_state['is_onetime']
    )


    state_machine_execution = sfn_client.start_execution(
        stateMachineArn=state_machine_arn,
        input=json.dumps(state_machine_input)
    )

    return {
      "statusCode": 200,
      "body" : json.dumps(s3_link)
    }
