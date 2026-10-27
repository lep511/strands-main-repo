from strands_harness import create_harness

agent = create_harness(model="bedrock/global.anthropic.claude-sonnet-4-6")
agent("Research the three most common strategies for versioning a REST API, compare their tradeoffs, and write a recommendation to api-versioning.md")
