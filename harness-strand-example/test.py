# import boto3

# # The calling identity needs bedrock-agentcore:InvokeWebSearch on
# # arn:aws:bedrock-agentcore:us-east-1:aws:tool/web-search.v1.
# REGION = "us-east-1"

# client = boto3.client("bedrock-agentcore", region_name=REGION)

# response = client.invoke_web_search(
#     webSearchId="web-search.v1",
#     searchQuery="Julio Cesar [spanish response]",
#     maxResults=10,
# )

# for result in response["results"]:
#     if "title" in result:
#         print(result["title"])
#     if "url" in result:
#         print(result["url"])
#     if "publishedAt" in result:
#         print(f"Published: {result['publishedAt']:%Y-%m-%d}")
#     print(result["text"][:200])
#     print()

import boto3

client = boto3.client('bedrock-agentcore', region_name='us-east-1')
response = client.invoke_code_interpreter(
    codeInterpreterIdentifier='aws.codeinterpreter.v1',
    sessionId='session1',  # Must be 33+ chars
    name='executeCode',
    arguments={
        'code':'print("Hello, world!")',
        'language':'python'
    }
)

response_body = response['response'].read()
response_data = json.loads(response_body)
print("Agent Response:", response_data)