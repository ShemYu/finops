import json
import requests
import os
from dotenv import load_dotenv


load_dotenv() 

SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")
DEBUG = True

def lambda_handler(event, context):
    if not SLACK_WEBHOOK_URL:
        return {
            "statusCode": 500,
            "body": "Error: SLACK_WEBHOOK_URL environment variable not set."
        }

    message = {
        "text": "🚀 Hello from AWS Lambda!"
    }

    try:
        response = requests.post(
            SLACK_WEBHOOK_URL,
            headers={"Content-Type": "application/json"},
            data=json.dumps(message)
        )
    
        if DEBUG:
            response = requests.post(
                SLACK_WEBHOOK_URL,
                headers={"Content-Type": "application/json"},
                data=json.dumps({"text": "Debug mode: " + json.dumps(event)})
            )

        if response.status_code != 200:
            return {
                "statusCode": 500,
                "body": f"Slack webhook failed: {response.text}"
            }

    except Exception as e:
        return {
            "statusCode": 500,
            "body": f"Error: {str(e)}"
        }

    return {
        "statusCode": 200,
        "body": "Message sent to Slack!"
    }

if __name__ == "__main__":
    lambda_handler(None, None)
