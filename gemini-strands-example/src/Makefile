build-WeatherAgentFunction:
	uv pip install -r requirements.txt \
		--target $(ARTIFACTS_DIR) \
		--python-version 3.13 \
		--python-platform manylinux2014_x86_64 \
		--refresh
	cp lambda_agent.py $(ARTIFACTS_DIR)