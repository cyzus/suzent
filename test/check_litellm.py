import litellm
from dotenv import load_dotenv

load_dotenv()


output = litellm.completion(
    model="litellm_proxy/xai_grok-4",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello, how are you?"},
    ]

)

print(output)