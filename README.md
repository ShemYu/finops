# finops

This project provides a Lambda function that sends notifications to Slack based on AWS EC2 instance state changes. It utilizes an EventBridge rule to trigger the Lambda function.

## Prerequisites

*   Docker
*   AWS CLI (configured with necessary permissions)
*   AWS SAM CLI (for local testing)
*   **Execution Environment:** The build and deployment commands (`make build`, `make deploy`, etc.) are designed to be executed on an EC2 instance within the same AWS account where the resources (ECR repository, Lambda function, EventBridge rule) will reside. This EC2 instance must have an IAM Role attached with the necessary permissions to:
    *   Push images to Amazon ECR.
    *   Update AWS Lambda functions.
    *   Deploy AWS CloudFormation stacks (for EventBridge, etc.).
    This setup avoids the need for explicit IAM role assumption scripts within the project.

## Development Workflow

### 1. Setup Environment

Before you begin, you need to set up your environment variables.

1.  Copy the example Makefile:
    ```bash
    cp Makefile.example Makefile
    ```
2.  Edit the `Makefile` and replace the placeholder values with your actual AWS Account ID, ECR Repository Name, and Lambda Function Name.
    *   `YOUR_AWS_ACCOUNT_ID`
    *   `YOUR_ECR_REPO_NAME`
    *   `YOUR_LAMBDA_FUNCTION_NAME`

    **Important:** The `Makefile` contains sensitive information and is included in `.gitignore` to prevent accidental commits to the repository.

### 2. Build Docker Image

To build the Docker image for the Lambda function:

```bash
make build
```

This command uses the `Dockerfile` in the project root to build an image tagged as `YOUR_ECR_REPO_NAME:latest` (or whatever you set as `YOUR_ECR_REPO_NAME` in the `Makefile`).

### 3. Tag Image for ECR

After building, tag the image for your Amazon ECR (Elastic Container Registry):

```bash
make tag
```

This will tag the image with the full ECR URI: `YOUR_AWS_ACCOUNT_ID.dkr.ecr.ap-northeast-1.amazonaws.com/YOUR_ECR_REPO_NAME:latest`.

### 4. Authenticate Docker with ECR & Push Image

To push the image to ECR, you first need to authenticate Docker with your AWS ECR private registry:

```bash
make auth
```

Then, push the tagged image:

```bash
make push
```

### 5. Update Lambda Function

Once the image is in ECR, update your Lambda function to use the new image:

```bash
make update
```

### Full Deploy Cycle

To run the entire deployment process (auth, build, tag, push, update) in one go:

```bash
make deploy
```

## Testing Locally

You can test the Lambda function locally using AWS SAM CLI before deploying.

1.  Ensure you have an `event.json` file in the root of your project. This file should contain the test event payload for your Lambda function.
2.  Run the local invocation:

    ```bash
    make test
    ```
    This command executes `sam local invoke SlackNotifyFunction -e event.json`, where `SlackNotifyFunction` is the logical ID of your function in your SAM template (if you are using one, or it's a conventional name for the test).

## Infrastructure as Code (IaC)

This project includes CloudFormation templates to set up necessary AWS resources. These templates are located in the `iac/cloudformation/` directory.

### EventBridge Rule for EC2 State Changes

The `iac/cloudformation/eventbridge.json` template creates an AWS EventBridge rule named `ec2-state-notify`. This rule is configured to:

*   Listen for EC2 instance state-change notifications (`running`, `terminated`, `stopping`).
*   Target the `dogi-slack-notification` Lambda function.

**Deployment:**

To deploy this CloudFormation stack, use the AWS CLI. Make sure your Lambda function (e.g., `dogi-slack-notification` as specified in the template) is already deployed.

```bash
aws cloudformation deploy \
  --template-file iac/cloudformation/eventbridge.json \
  --stack-name Ec2StateChangeToSlackRule \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM
```

**Note:**
*   Ensure your AWS CLI is configured with the necessary permissions to create EventBridge rules and related resources.
*   The CloudFormation template `iac/cloudformation/eventbridge.json` targets a Lambda function named `dogi-slack-notification`. If your Lambda function has a different name, you must update the `Arn` within the `Targets` section of the `eventbridge.json` file before deploying this stack.