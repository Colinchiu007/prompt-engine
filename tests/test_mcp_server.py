"""MCP Server 基础启动测试."""
import pytest


class TestMCPServer:
    """MCP Server 能正常启动并列出工具."""

    def test_mcp_server_imports(self):
        """MCP Server 模块可正常导入（不依赖外部连接）."""
        from prompt_engine.api.mcp_server import server
        assert server is not None

    def test_mcp_tools_registered(self):
        """MCP Server 注册了关键工具."""
        from prompt_engine.api.mcp_server import handle_list_tools
        import asyncio
        tools = asyncio.run(handle_list_tools())
        tool_names = [tool.name for tool in tools]
        assert "optimize_prompt" in tool_names
        assert "reverse_prompt" in tool_names

    def test_mcp_config(self):
        """MCP Server 配置不为空."""
        from prompt_engine.api.mcp_server import server
        assert server is not None

    @pytest.mark.asyncio
    async def test_optimize_schema_strategy_contract(self):
        from prompt_engine.api.mcp_server import handle_list_tools

        tools = await handle_list_tools()
        optimize = next(tool for tool in tools if tool.name == "optimize_prompt")
        strategy = optimize.inputSchema["properties"]["optimization_strategy"]
        assert strategy["enum"] == ["template", "llm"]
        assert strategy["default"] == "llm"
        assert optimize.inputSchema["properties"]["llm"]["required"] == ["provider", "model", "api_key"]
        reverse = next(tool for tool in tools if tool.name == "reverse_prompt")
        assert "llm" in reverse.inputSchema["properties"]
        assert reverse.inputSchema["required"] == ["image_url", "llm"]

    @pytest.mark.asyncio
    async def test_optimize_requires_byok_unless_explicit_template(self):
        from prompt_engine.api.mcp_server import _handle_optimize

        with pytest.raises(ValueError, match="llm 必填"):
            await _handle_optimize({"prompt": "a cat"})

        result = await _handle_optimize({
            "prompt": "a cat",
            "optimization_strategy": "template",
            "creative_level": 10,
        })
        assert result[0].text

    @pytest.mark.asyncio
    async def test_reverse_requires_byok(self):
        from prompt_engine.api.mcp_server import _handle_reverse

        with pytest.raises(ValueError, match="llm 必填"):
            await _handle_reverse({"image_url": "https://example.com/cat.jpg"})

    @pytest.mark.asyncio
    async def test_optimize_rejects_unknown_strategy_before_provider_resolution(self):
        from prompt_engine.api.mcp_server import _handle_optimize

        with pytest.raises(ValueError, match="optimization_strategy"):
            await _handle_optimize({
                "prompt": "a cat",
                "optimization_strategy": "auto",
                "llm": {
                    "provider": "openai_compat",
                    "model": "gpt-4o",
                    "api_key": "test-key",
                },
            })
