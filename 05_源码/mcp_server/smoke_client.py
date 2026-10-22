from __future__ import annotations

import argparse
import asyncio
import json

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def run(url: str) -> None:
    async with streamablehttp_client(url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
            tool_names = [tool.name for tool in tools.tools]
            print(json.dumps({"available_tools": tool_names}, ensure_ascii=False))

            calls = [
                ("get_student_profile", {"student_id": "demo"}),
                ("get_role_competency", {"role_id": "job_001"}),
            ]
            for name, arguments in calls:
                result = await session.call_tool(name, arguments)
                payload = result.structuredContent
                if payload is None:
                    payload = [getattr(item, "text", str(item)) for item in result.content]
                print(json.dumps({"tool": name, "is_error": result.isError, "result": payload}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Call the local ICT AgentArts MCP server.")
    parser.add_argument("--url", default="http://127.0.0.1:8010/mcp")
    args = parser.parse_args()
    asyncio.run(run(args.url))


if __name__ == "__main__":
    main()

