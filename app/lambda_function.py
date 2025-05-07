import json
import logging
import os
from datetime import datetime, timedelta, timezone
import random

import boto3
import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger()
logger.setLevel(logging.INFO)
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")


def get_instance_info(instance_id, region):
    ec2 = boto3.client("ec2", region_name=region)
    response = ec2.describe_instances(InstanceIds=[instance_id])
    instance = response["Reservations"][0]["Instances"][0]

    instance_type = instance["InstanceType"]
    tags = {tag["Key"]: tag["Value"] for tag in instance.get("Tags", [])}

    root_volume = next(
        (
            b
            for b in instance["BlockDeviceMappings"]
            if b.get("DeviceName") == instance["RootDeviceName"]
        ),
        None,
    )
    ebs_id = root_volume["Ebs"]["VolumeId"] if root_volume else "unknown"
    ebs_info = ec2.describe_volumes(VolumeIds=[ebs_id]).get("Volumes", [])
    ebs_size = ebs_info[0].get("Size", "unknown")
    ebs_type = ebs_info[0].get("VolumeType", "unknown")

    return {
        "instance_type": instance_type,
        "name": tags.get("Name", "N/A"),
        "ebs_volume_size": ebs_size,
        "ebs_volume_type": ebs_type,
        "tags": tags,
    }


def get_creator_of_instance(instance_id, region, event_state, lookback_days=7):
    ct = boto3.client("cloudtrail", region_name=region)
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(days=lookback_days)
    event_state_attribute_value_mapping = {
        "running": "RunInstances",
        "terminated": "TerminateInstances",
        "stopping": "StopInstances",
    }

    # 只按 EventName 查
    resp = ct.lookup_events(
        LookupAttributes=[
            {
                "AttributeKey": "EventName",
                "AttributeValue": event_state_attribute_value_mapping[event_state],
            }
        ],
        StartTime=start_time,
        EndTime=end_time,
        MaxResults=50,
    )

    for event_rec in resp.get("Events", []):
        evt = json.loads(event_rec["CloudTrailEvent"])
        # 核对 responseElements 里有没有这台 instance
        items = evt.get("responseElements", {}).get("instancesSet", {}).get("items", [])
        ids = [it.get("instanceId") for it in items]
        if instance_id in ids:
            user = evt["userIdentity"]["arn"]
            return {
                "time": event_rec["EventTime"]
                .astimezone(timezone(timedelta(hours=8)))
                .strftime("%Y%m%d %H:%M:%S"),
                "user_arn": user,
                "username": evt["userIdentity"].get("userName", "<role>"),
            }
    return None


def send_ec2_event_to_slack(instance_info, creator_info, action_type, region, instance_id):
    """
    instance_info: {
      "instance_type": str,
      "name": str,
      "ebs_volume_size": int,      # GiB
      "ebs_volume_type": str,
      "tags": dict
    }
    creator_info: {
      "time": str,                 # ISO timestamp
      "user_arn": str,
      "username": str
    }
    """
    action_title_map = {
        "running": "🚀 EC2 Instance Started 🚀",
        "terminated": "💀 EC2 Instance Terminated 💀",
        "stopping": "😴 EC2 Instance Stopping 😴",
    }
    reminders = [
        "Billing is charging from this moment.",
        "Hourly charges are now in effect.",
        "Running and generating costs.",
        "Monitor usage to control expenses.",
        "Ensure you stop the instance when not needed."
    ]
    ec2_stop_reminders = [
        "EBS volume storage charges continuely.",
        "Persistent EBS and allocated Elastic IP COSTS still apply.",
        "Stopping an EC2 instance does not STOP EBS or Elastic IP COSTS.",
        "EC2 instance is stopped; you will continue to incur EBS volume FEES.",
        "Remember to release Elastic IPs and delete unused volumes to avoid CHARGES."
    ]
    action_sub_title_map = {
        "running": reminders[random.randint(0, len(reminders) - 1)],
        "terminated": f"Good job {creator_info['username']} 🥰🥰🥰",
        "stopping": ec2_stop_reminders[random.randint(0, len(ec2_stop_reminders) - 1)],
    }
    ebs_warning = "\n⚠️ Large EBS ⚠️" if int(instance_info['ebs_volume_size']) > 1024 else ""
    # 1️⃣ 組出 Slack blocks
    blocks = [
        {
			"type": "header",
			"text": {
				"type": "plain_text",
				"text": action_title_map[action_type],
				"emoji": True
			}
		},
        {
			"type": "section",
			"text": {
				"type": "plain_text",
				"text": action_sub_title_map[action_type],
				"emoji": True
			}
		},
        {"type": "divider"},
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Name:*\n{instance_info['name']}"},
                {
                    "type": "mrkdwn",
                    "text": f"*Type:*\n{instance_info['instance_type']}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*EBS:*\n{instance_info['ebs_volume_size']} GiB ({instance_info['ebs_volume_type']})" + ebs_warning,
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Tags:*\n```{json.dumps(instance_info['tags'], ensure_ascii=False)}```",
                },
            ],
        },
        {"type": "divider"},
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Action By:*\n{creator_info['username']}"},
                {"type": "mrkdwn", "text": f"*IAM ARN:*\n{creator_info['user_arn']}"},
                {"type": "mrkdwn", "text": f"*Action Type:*\n{action_type}"},
                {"type": "mrkdwn", "text": f"*Action Time:*\n{creator_info['time']}"},
            ],
        },
        {
			"type": "section",
			"text": {
				"type": "mrkdwn",
				"text": "For more detail information 👉"
			},
			"accessory": {
				"type": "button",
				"text": {
					"type": "plain_text",
					"text": "Go To AWS EC2",
					"emoji": True
				},
				"value": "click_me_123",
				"url": f"https://{region}.console.aws.amazon.com/ec2/home?region={region}#InstanceDetails:instanceId={instance_id}",
				"action_id": "button-action"
			}
		}
    ]

    payload = {"blocks": blocks}

    return payload


def send_message(message):
    response = requests.post(
        SLACK_WEBHOOK_URL,
        headers={"Content-Type": "application/json"},
        data=json.dumps(message),
    )
    if response.status_code != 200:
        return {"statusCode": 500, "body": f"Slack webhook failed: {response.text}"}


def lambda_handler(event, context):
    if not SLACK_WEBHOOK_URL:
        return {
            "statusCode": 500,
            "body": "Error: SLACK_WEBHOOK_URL environment variable not set.",
        }

    try:
        instance_info = get_instance_info(
            event["detail"]["instance-id"], event["region"]
        )
        creator_info = get_creator_of_instance(
            event["detail"]["instance-id"],
            event["region"],
            event["detail"]["state"],
        )
        block = send_ec2_event_to_slack(
            instance_info, creator_info, event["detail"]["state"], event["region"], event["detail"]["instance-id"]
        )
        send_message(block)
    except Exception as e:
        return {"statusCode": 500, "body": f"Error: {str(e)}"}

    return {"statusCode": 200, "body": "Message sent to Slack!"}


if __name__ == "__main__":
    # lambda_handler(None, None)
    # instance_info = get_instance_info("i-0e1aecda99aa63792")
    # print(instance_info)
    pass
