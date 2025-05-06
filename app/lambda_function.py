import json
import requests

SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/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"  # 你的 webhook 填這邊

def lambda_handler(event, context):
    message = {
        "text": "🚀 Hello from AWS Lambda!"
    }

    try:
        response = requests.post(
            SLACK_WEBHOOK_URL,
            headers={"Content-Type": "application/json"},
            data=json.dumps(message)
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
