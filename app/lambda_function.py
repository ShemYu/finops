import json
import logging
import os
import random
from datetime import datetime, timedelta, timezone

import boto3
import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger()
logger.setLevel(logging.INFO)
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")


def get_instance_info(instance_id, region):
    """Retrieves detailed information about a specific EC2 instance.

    Args:
        instance_id (str): The ID of the EC2 instance.
        region (str): The AWS region where the instance is located.

    Returns:
        dict: A dictionary containing instance details such as instance type,
            name tag, EBS volume size, EBS volume type, and all tags.
            Returns 'unknown' for EBS details if not found.
            Example:
            {
                "instance_type": "t2.micro",
                "name": "my-instance",
                "ebs_volume_size": 8,
                "ebs_volume_type": "gp2",
                "tags": {"Name": "my-instance", "Environment": "dev"}
            }
    """
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
    if instance_state := response['Reservations'][0]['Instances'][0]['State']['Name'] != "terminated":
        ebs_info = ec2.describe_volumes(VolumeIds=[ebs_id]).get("Volumes", [])
        ebs_size = ebs_info[0].get("Size", "unknown")
        ebs_type = ebs_info[0].get("VolumeType", "unknown")
    else:
        ebs_size = 0
        ebs_type = "unknown"

    return {
        "instance_type": instance_type,
        "name": tags.get("Name", "N/A"),
        "ebs_volume_size": ebs_size,
        "ebs_volume_type": ebs_type,
        "tags": tags,
    }


def get_creator_of_instance(
    instance_id: str, region: str, event_state: str, lookback_days: int = 7
):
    """Identifies the IAM user or role that initiated an EC2 instance state change.

    This function queries AWS CloudTrail logs for events corresponding to the
    specified instance ID and event state (e.g., "running", "stopping",
    "terminated"). It handles pagination to search through CloudTrail events
    within the lookback period. It checks for the instance ID in both
    `responseElements.instancesSet.items` and `requestParameters.instancesSet.items`
    of the CloudTrail event record.

    Args:
        instance_id (str): The ID of the EC2 instance.
        region (str): The AWS region where the instance is located.
        event_state (str): The target state of the instance. Supported values
            are "running" (maps to RunInstances, StartInstances),
            "stopping" (maps to StopInstances), and "terminated"
            (maps to TerminateInstances).
        lookback_days (int, optional): The number of days to look back in
            CloudTrail logs. Defaults to 7.

    Returns:
        dict: A dictionary containing the event time, user ARN, and username
            of the entity that performed the action. The time is formatted
            as 'YYYYMMDD HH:MM:SS' in UTC+8. Returns None if no
            matching event is found.
            Example:
            {
                "time": "20230101 10:00:00",
                "user_arn": "arn:aws:iam::123456789012:user/johndoe",
                "username": "johndoe"
            }
        None: If no relevant CloudTrail event is found for the instance.

    Raises:
        ValueError: If an unsupported `event_state` is provided.
    """
    ct = boto3.client("cloudtrail", region_name=region)
    now = datetime.utcnow().replace(tzinfo=timezone.utc)
    start_time = now - timedelta(days=lookback_days)

    name_map = {
        "running": ["RunInstances", "StartInstances"],
        "stopping": ["StopInstances"],
        "terminated": ["TerminateInstances"],
    }
    event_names = name_map.get(event_state.lower())
    if not event_names:
        raise ValueError(f"unsupported event_state: {event_state}")

    # Iterate through each relevant event name
    for event_name in event_names:
        next_token = None
        while True:
            # Correctly construct kwargs for the current event name
            kwargs = {
                "LookupAttributes": [{"AttributeKey": "EventName", "AttributeValue": event_name}],
                "StartTime": start_time,
                "EndTime": now,
                "MaxResults": 50,
            }
            if next_token:
                kwargs["NextToken"] = next_token

            try: # Add error handling for the API call
                resp = ct.lookup_events(**kwargs)
            except Exception as e:
                logger.error(f"Error calling lookup_events for {event_name}: {e}")
                break # Break inner loop on error for this event name

            for event_rec in resp.get("Events", []):
                try: # Add error handling for JSON parsing and key access
                    evt = json.loads(event_rec["CloudTrailEvent"])

                    # Check responseElements first
                    items = (
                        evt.get("responseElements", {})
                        .get("instancesSet", {})
                        .get("items", [])
                    )

                    # If not found, check requestParameters
                    if not items:
                        items = (
                            evt.get("requestParameters", {})
                            .get("instancesSet", {})
                            .get("items", [])
                        )

                    ids = [it.get("instanceId") for it in items if it.get("instanceId")] # Ensure instanceId exists
                    logger.debug(f"event {event_rec['EventName']} ids: {ids}")

                    if instance_id in ids:
                        user_identity = evt.get("userIdentity", {})
                        user_arn = user_identity.get("arn")
                        # Extract username, handle different identity types
                        username = user_identity.get("userName")
                        if not username:
                             # Handle assumed roles, federated users, etc.
                            session_context = user_identity.get("sessionContext", {})
                            issuer_arn = session_context.get("sessionIssuer", {}).get("arn")
                            if issuer_arn:
                                username = f"{issuer_arn.split('/')[-1]} (AssumedRole)"
                            elif user_identity.get("type") == "AssumedRole":
                                username = f"{user_arn.split('/')[-2].split(':')[-1]}/{user_arn.split('/')[-1]} (AssumedRole)" # Extract role name and session name
                            elif user_identity.get("type") == "FederatedUser":
                                username = user_arn.split('/')[-1] + " (Federated)"
                            elif user_identity.get("type") == "AWSAccount":
                                username = f"Account:{user_identity.get('accountId')}"
                            else:
                                username = user_identity.get("type", "<unknown_identity>") # Fallback


                        if user_arn: # Ensure we found an ARN
                            return {
                                "time": event_rec["EventTime"]
                                .astimezone(timezone(timedelta(hours=8)))
                                .strftime("%Y%m%d %H:%M:%S"),
                                "user_arn": user_arn,
                                "username": username,
                            }
                except (json.JSONDecodeError, KeyError, AttributeError) as e:
                    logger.error(f"Error processing event record: {e}\nRecord: {event_rec}")
                    continue # Skip malformed or unexpected event records

            next_token = resp.get("NextToken")
            if not next_token:
                break # Exit pagination loop for the current event_name

    # If no event was found after checking all event_names
    logger.info(f"No CloudTrail event found for instance {instance_id} with state {event_state}")
    return None


def send_ec2_event_to_slack(
    instance_info, creator_info, action_type, region, instance_id
):
    """Constructs a Slack message payload for EC2 instance state change events.

    The message includes instance details, creator information, and relevant
    reminders or warnings based on the action type (running, terminated, stopping).

    Args:
        instance_info (dict): Information about the EC2 instance. Expected keys:
            "instance_type" (str): The type of the instance (e.g., "t2.micro").
            "name" (str): The 'Name' tag of the instance, or "N/A".
            "ebs_volume_size" (int or str): Size of the root EBS volume in GiB.
            "ebs_volume_type" (str): Type of the root EBS volume (e.g., "gp2").
            "tags" (dict): All tags associated with the instance.
        creator_info (dict): Information about the user who initiated the action.
            Expected keys:
            "time" (str): Timestamp of the action (e.g., "20230101 10:00:00").
            "user_arn" (str): ARN of the IAM user/role.
            "username" (str): Username or role name.
        action_type (str): The type of EC2 action ("running", "terminated",
            "stopping").
        region (str): The AWS region of the instance.
        instance_id (str): The ID of the EC2 instance.

    Returns:
        dict: A Slack message payload formatted with blocks.
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
        "Ensure you stop the instance when not needed.",
    ]
    ec2_stop_reminders = [
        "EBS volume storage charges continuely.",
        "Persistent EBS and allocated Elastic IP COSTS still apply.",
        "Stopping an EC2 instance does not STOP EBS or Elastic IP COSTS.",
        "EC2 instance is stopped; you will continue to incur EBS volume FEES.",
        "Remember to release Elastic IPs and delete unused volumes to avoid CHARGES.",
    ]
    action_sub_title_map = {
        "running": reminders[random.randint(0, len(reminders) - 1)],
        "terminated": f"Good job {creator_info['username']} 🥰🥰🥰",
        "stopping": ec2_stop_reminders[random.randint(0, len(ec2_stop_reminders) - 1)],
    }
    ebs_warning = (
        "\n⚠️ Large EBS ⚠️" if int(instance_info["ebs_volume_size"]) > 1024 else ""
    )
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": action_title_map[action_type],
                "emoji": True,
            },
        },
        {
            "type": "section",
            "text": {
                "type": "plain_text",
                "text": action_sub_title_map[action_type],
                "emoji": True,
            },
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
                    "text": f"*EBS:*\n{instance_info['ebs_volume_size']} GiB ({instance_info['ebs_volume_type']})"
                    + ebs_warning,
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
            "text": {"type": "mrkdwn", "text": "For more detail information 👉"},
            "accessory": {
                "type": "button",
                "text": {"type": "plain_text", "text": "Go To AWS EC2", "emoji": True},
                "value": "click_me_123",
                "url": f"https://{region}.console.aws.amazon.com/ec2/home?region={region}#InstanceDetails:instanceId={instance_id}",
                "action_id": "button-action",
            },
        },
    ]

    payload = {"blocks": blocks}

    return payload


def send_message(message):
    """Sends a message payload to the configured Slack webhook URL.

    Args:
        message (dict): The Slack message payload (e.g., a blocks structure).

    Returns:
        dict: A dictionary with "statusCode" and "body" indicating the result
            of the Slack API call. Returns status code 500 on failure.
    """
    response = requests.post(
        SLACK_WEBHOOK_URL,
        headers={"Content-Type": "application/json"},
        data=json.dumps(message),
    )
    if response.status_code != 200:
        return {"statusCode": 500, "body": f"Slack webhook failed: {response.text}"}


def lambda_handler(event, context):
    """AWS Lambda handler function for processing EC2 state change events.

    This function is triggered by an AWS EventBridge rule when an EC2 instance
    changes state. It gathers instance information, identifies the event creator,
    constructs a Slack message, and sends it.

    Args:
        event (dict): The event payload from EventBridge. Expected to contain
            `event["detail"]["instance-id"]`, `event["region"]`, and
            `event["detail"]["state"]`.
        context (object): The AWS Lambda runtime information. Not used directly
            in this function but required by the Lambda signature.

    Returns:
        dict: A dictionary with "statusCode" and "body" indicating the outcome.
            Returns status code 200 on success, 500 on error.
    """
    if not SLACK_WEBHOOK_URL:
        return {
            "statusCode": 500,
            "body": "Error: SLACK_WEBHOOK_URL environment variable not set.",
        }

    # try:
    instance_info = get_instance_info(event["detail"]["instance-id"], event["region"])
    logger.info(instance_info)
    creator_info = get_creator_of_instance(
        event["detail"]["instance-id"],
        event["region"],
        event["detail"]["state"],
    )
    logger.info(creator_info)
    block = send_ec2_event_to_slack(
        instance_info,
        creator_info,
        event["detail"]["state"],
        event["region"],
        event["detail"]["instance-id"],
    )
    send_message(block)
    # except Exception as e:
    #     return {"statusCode": 500, "body": f"Error: {str(e)}"}

    return {"statusCode": 200, "body": "Message sent to Slack!"}


if __name__ == "__main__":
    # lambda_handler(None, None)
    # instance_info = get_instance_info("i-0e1aecda99aa63792")
    # print(instance_info)
    pass
