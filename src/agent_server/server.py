from mcp.server.fastmcp import FastMCP
from agent_server.tools import (
    chat_init,
    job_title, 
    seniority, 
    resume, 
    grade_resume,
    config,
    grading_results
)
from config import AgentConfig



mcp = FastMCP(
    name=AgentConfig.MCP_SERVER_NAME.value,
    host=AgentConfig.MCP_SERVER_HOST.value,
    port=AgentConfig.MCP_SERVER_PORT.value,
    json_response=True,
)

chat_init.register(mcp)
seniority.register(mcp)
job_title.register(mcp)
resume.register(mcp)
grade_resume.register(mcp)
config.register(mcp)
grading_results.register(mcp)

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
