build:
	docker build -t dogi/slack-notify .
tag:
	docker tag dogi/slack-notify:latest 767397933116.dkr.ecr.ap-northeast-1.amazonaws.com/dogi/slack-notify:latest
push:
	docker push 767397933116.dkr.ecr.ap-northeast-1.amazonaws.com/dogi/slack-notify:latest
test:
	sam local invoke SlackNotifyFunction -e event.json
update:
	aws lambda update-function-code \
		--function-name dogi-slack-notification \
		--image-uri 767397933116.dkr.ecr.ap-northeast-1.amazonaws.com/dogi/slack-notify:latest
