import litellm
from dotenv import load_dotenv

load_dotenv()

litellm_model_to_test = "litellm_proxy/xai_grok-4"

output = litellm.completion(
    model=litellm_model_to_test,
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello, how are you?"},
    ]

)

print(output)