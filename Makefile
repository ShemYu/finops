include .env
export $(shell sed 's/=.*//' .env)

auth:
	aws ecr get-login-password --region ap-northeast-1 | docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.ap-northeast-1.amazonaws.com
build:
	docker build -t ${ECR_REPO_NAME} .
tag:
	docker tag ${ECR_REPO_NAME}:latest ${AWS_ACCOUNT_ID}.dkr.ecr.ap-northeast-1.amazonaws.com/${ECR_REPO_NAME}:latest
push:
	docker push ${AWS_ACCOUNT_ID}.dkr.ecr.ap-northeast-1.amazonaws.com/${ECR_REPO_NAME}:latest
test:
	sam local invoke SlackNotifyFunction -e event.json
update:
	aws lambda update-function-code \
		--function-name ${LAMBDA_FUNCTION_NAME} \
		--image-uri ${AWS_ACCOUNT_ID}.dkr.ecr.ap-northeast-1.amazonaws.com/${ECR_REPO_NAME}:latest
deploy:
	make auth
	make build
	make tag
	make push
	make update
