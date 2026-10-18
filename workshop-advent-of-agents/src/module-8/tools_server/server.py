"""MCP server for the order tools, hosted on AgentCore Runtime (protocol MCP).

AgentCore Runtime's MCP contract: stateless streamable HTTP on 0.0.0.0:8000/mcp.
This file is packaged with mcp<2 (see requirements.txt), whose FastMCP matches that contract.
"""

from mcp.server.fastmcp import FastMCP

from orders import TOOLS

mcp = FastMCP(host="0.0.0.0", stateless_http=True)
for fn in TOOLS:
    mcp.tool()(fn)

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
