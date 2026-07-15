import json
import boto3

def invoke_mode():
    session = boto3.Session()
    bedrock = session.client(service_name='bedrock-runtime') #creates a Bedrock client

    bedrock_model_id = "us.amazon.nova-2-lite-v1:0"

    prompt = "What is the largest city in New Hampshire?" #the prompt to send to the model

    messages = [
        {
            "role": "user",
            "content": [
                {"text": prompt}
            ]
        }
    ]

    body = json.dumps({
        "schemaVersion": "messages-v1",
        "messages": messages,
        "inferenceConfig": {
            "maxTokens": 1024,
            "topP": 0.5,
            "topK": 20,
            "temperature": 0.0
        }
    }) #build the request payload

    response = bedrock.invoke_model(body=body, modelId=bedrock_model_id, accept='application/json', contentType='application/json')
    response_body = json.loads(response.get('body').read()) # read the response

    response_text = response_body["output"]["message"]["content"][0]["text"] #extract the text from the JSON response

    print(response_text)

def converse_mode():
    client = boto3.client("bedrock-runtime", region_name="us-east-1")  

    response = client.converse( 
        modelId="us.anthropic.claude-haiku-4-5-20251001-v1:0", 
        messages=[ 
            { 
                "role": "user", 
                "content": [{"text": "What is the largest city in New Hampshire?"}]
            } 
        ] 
    )  

    print(response["output"]["message"]["content"][0]["text"])


if __name__ == "__main__":
    invoke_mode()
    converse_mode()
