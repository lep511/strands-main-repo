import {
  registerAppResource,
  registerAppTool,
  RESOURCE_MIME_TYPE,
} from "@modelcontextprotocol/ext-apps/server";
import type {
  McpServer,
  CallToolResult,
  ReadResourceResult,
} from "@modelcontextprotocol/server";
import { McpServer as McpServerImpl } from "@modelcontextprotocol/server";
import fs from "node:fs/promises";
import path from "node:path";
import { z } from "zod";

const DIST_DIR = import.meta.filename.endsWith(".ts")
  ? path.join(import.meta.dirname, "dist")
  : import.meta.dirname;

const AGENT_URL = process.env.AGENT_URL ?? "http://localhost:8100";

export function createServer(): McpServer {
  const server = new McpServerImpl({
    name: "Strands Agent MCP App",
    version: "1.0.0",
  });

  const resourceUri = "ui://strands-agent/mcp-app.html";

  registerAppTool(
    server,
    "ask-agent",
    {
      title: "Ask Strands Agent",
      description:
        "Send a message to the Strands AI agent. The agent can check weather for cities and do math calculations.",
      inputSchema: z.object({
        message: z
          .string()
          .describe("The message or question to send to the agent"),
      }),
      outputSchema: z.object({
        message: z.string(),
        response: z.string(),
        tools_used: z.array(z.string()),
      }),
      _meta: { ui: { resourceUri } },
    },
    async (args): Promise<CallToolResult> => {
      try {
        const res = await fetch(`${AGENT_URL}/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: args.message }),
        });

        if (!res.ok) {
          const text = await res.text();
          return {
            content: [{ type: "text", text: `Agent error: ${text}` }],
            isError: true,
          };
        }

        const data = (await res.json()) as {
          response: string;
          tools_used: string[];
        };

        return {
          content: [{ type: "text", text: data.response }],
          structuredContent: {
            message: args.message,
            response: data.response,
            tools_used: data.tools_used ?? [],
          },
        };
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        return {
          content: [
            {
              type: "text",
              text: `Failed to reach Strands agent at ${AGENT_URL}: ${msg}`,
            },
          ],
          isError: true,
        };
      }
    },
  );

  registerAppResource(
    server,
    resourceUri,
    resourceUri,
    { mimeType: RESOURCE_MIME_TYPE },
    async (): Promise<ReadResourceResult> => {
      const html = await fs.readFile(
        path.join(DIST_DIR, "mcp-app.html"),
        "utf-8",
      );
      return {
        contents: [
          { uri: resourceUri, mimeType: RESOURCE_MIME_TYPE, text: html },
        ],
      };
    },
  );

  return server;
}
