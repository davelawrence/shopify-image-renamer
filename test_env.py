from dotenv import load_dotenv
import os

dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path=dotenv_path)

print("AWS_S3_BUCKET =", os.getenv('AWS_S3_BUCKET'))
print("AWS_S3_REGION =", os.getenv('AWS_S3_REGION'))
print("TEST_ENV_VAR =", os.getenv('TEST_ENV_VAR'))