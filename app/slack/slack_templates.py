import json
import random

def create_ec2_event_message(
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
        "terminated": f"Good job {creator_info.get('username', 'Unknown')} 🥰🥰🥰",
        "stopping": ec2_stop_reminders[random.randint(0, len(ec2_stop_reminders) - 1)],
    }
    # Ensure ebs_volume_size is treated as a number for comparison
    try:
        # Use .get() to provide a default value if the key is missing
        ebs_size = int(instance_info.get("ebs_volume_size", 0))
    except (ValueError, TypeError):
        ebs_size = 0 # Default or handle error appropriately if conversion fails

    ebs_warning = "\n⚠️ Large EBS ⚠️" if ebs_size > 1024 else ""

    # Use .get() for all dictionary accesses to prevent KeyError
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": action_title_map.get(action_type, f"ℹ️ EC2 Instance {action_type.capitalize()} ℹ️"), # Default title for unknown actions
                "emoji": True,
            },
        },
        {
            "type": "section",
            "text": {
                "type": "plain_text",
                "text": action_sub_title_map.get(action_type, f"Instance state changed to {action_type}."), # Default subtitle
                "emoji": True,
            },
        },
        {"type": "divider"},
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Name:*\n{instance_info.get('name', 'N/A')}"},
                {
                    "type": "mrkdwn",
                    "text": f"*Type:*\n{instance_info.get('instance_type', 'N/A')}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*EBS:*\n{instance_info.get('ebs_volume_size', 'N/A')} GiB ({instance_info.get('ebs_volume_type', 'N/A')})"
                    + ebs_warning,
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Tags:*\n```{json.dumps(instance_info.get('tags', {}), ensure_ascii=False)}```",
                },
            ],
        },
        {"type": "divider"},
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Action By:*\n{creator_info.get('username', 'Unknown')}"},
                {"type": "mrkdwn", "text": f"*IAM ARN:*\n{creator_info.get('user_arn', 'Unknown')}"},
                {"type": "mrkdwn", "text": f"*Action Type:*\n{action_type}"},
                {"type": "mrkdwn", "text": f"*Action Time:*\n{creator_info.get('time', 'Unknown')}"},
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


def create_simple_ec2_event_message(
    instance_info, creator_info, action_type, region, instance_id
):
    """Constructs a simpler Slack message payload for EC2 instance state change events.

    Args:
        instance_info (dict): Information about the EC2 instance.
        creator_info (dict): Information about the user who initiated the action.
        action_type (str): The type of EC2 action ("running", "terminated", "stopping").
        region (str): The AWS region of the instance.
        instance_id (str): The ID of the EC2 instance.

    Returns:
        dict: A simple Slack message payload formatted with blocks.
    """
    action_verb_map = {
        "running": "Started",
        "terminated": "Terminated",
        "stopping": "Stopping",
        "stopped": "Stopped", # Added for completeness
    }
    action_verb = action_verb_map.get(action_type, action_type.capitalize())

    # Get info safely using .get()
    instance_name = instance_info.get('name', 'N/A')
    instance_type = instance_info.get('instance_type', 'N/A')
    username = creator_info.get('username', 'Unknown')

    title = f"EC2 Instance {action_verb}: {instance_name} ({instance_id})"
    details = f"*Type:* {instance_type} | *Region:* {region} | *User:* {username}"

    # New block message
    blocks = {
        "blocks": [
            {
                "type": "context",
                "elements": [
                    {
                        "type": "image",
                        "image_url": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRULf2JOHbvkPux8pEzQrkH70TVSpfgRMzgQA&s",
                        "alt_text": "EC2 instance"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*{instance_name}* is *{action_verb}* by *{username}*"
                    }
                ]
            }
        ]
    }
    if action_verb == "Started":
        blocks["blocks"][0]["elements"].append(
            {
                "type": "image",
                "image_url": "https://em-content.zobj.net/source/noto-emoji-animations/344/rocket_1f680.gif",
                "alt_text": "space ship"
            }
        )
    elif action_verb == "Stopping":
        blocks["blocks"][0]["elements"].append(
            {
                "type": "image",
                "image_url": "https://em-content.zobj.net/source/animated-noto-color-emoji/356/sleeping-face_1f634.gif",
                "alt_text": "sleepy"
            }
        )
    elif action_verb == "Terminated":
        blocks["blocks"][0]["elements"].append(
            {
                "type": "image",
                "image_url": "https://em-content.zobj.net/source/animated-noto-color-emoji/356/money-mouth-face_1f911.gif",
                "alt_text": "rich"
            }
        )
    return blocks
