FROM public.ecr.aws/lambda/python:3.12

# 複製依賴與程式碼
COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install -r ${LAMBDA_TASK_ROOT}/requirements.txt

COPY app/lambda_function.py ${LAMBDA_TASK_ROOT}/
COPY .env ${LAMBDA_TASK_ROOT}/

# 設定 handler：module_name.function_name
CMD [ "lambda_function.lambda_handler" ]
