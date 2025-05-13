FROM public.ecr.aws/lambda/python:3.12

# 複製依賴與程式碼
COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install -r ${LAMBDA_TASK_ROOT}/requirements.txt

# Copy the entire app directory
COPY app/ ${LAMBDA_TASK_ROOT}/app/
COPY .env ${LAMBDA_TASK_ROOT}/

# Set handler: directory.module_name.function_name
CMD [ "app.lambda_function.lambda_handler" ]
