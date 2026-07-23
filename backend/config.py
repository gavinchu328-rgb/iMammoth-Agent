from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openclaw_base_url: str = "http://127.0.0.1:18789"
    openclaw_api_key: str = "a5c48bbab43af2819dd167088ca27a84bd6d3ff5ac81304e"
    # 默认通用对话走 main；AI4Drug 技能走 ai4drug（见 openclaw_route）
    openclaw_agent_id: str = "main"
    openclaw_model: str = "openclaw:main"
    openclaw_ai4drug_agent_id: str = "ai4drug"
    openclaw_ai4drug_model: str = "openclaw:ai4drug"
    openclaw_system_prompt: str = (
        "你是猛犸智能体助手。"
        "在任何可用的情况下，必须先优先匹配并调用已安装的技能/工具完成任务，再用工具结果回答。"
        "语言硬性要求：对用户回答、分析过程、以及内部 thinking/推理过程一律使用简体中文；"
        "禁止用英文写思考过程。工具名、路径、命令、代码、SMILES 等可保留原文，说明文字必须中文。"
        "品牌要求：对用户一律称「猛犸智能体」，禁止出现 OpenClaw Agent；"
        "禁止输出「正在通过 OpenClaw Agent 处理您的请求」等占位语。"
    )

    db_host: str = "127.0.0.1"
    db_port: int = 5434
    db_user: str = "oakclaw"
    db_password: str = "oakclaw_password"
    db_name: str = "mammoth_agent"

    backend_port: int = 8080
    skills_path: str = "../skills/skills.yaml"
    databases_path: str = "../data/databases.yaml"
    process_log_spec_path: str = "../docs/process_log_spec.md"
    process_log_dir: str = "/data2/mammoth-agent/process_logs"
    openclaw_sessions_root: str = "/home/dbcloud/.openclaw/agents"
    openclaw_sessions_index: str = "/home/dbcloud/.openclaw/agents/main/sessions/sessions.json"

    # 流式过程 / 长任务超时（秒）
    stream_poll_interval_sec: float = 0.2
    stream_short_idle_sec: float = 5.0
    stream_general_sec: float = 600.0
    stream_skill_default_sec: float = 600.0
    mcp_tool_timeout_ms: int = 600_000  # mcporter --timeout 单位为毫秒，10 分钟
    stream_ai4drug_fast_sec: float = 600.0
    stream_ai4drug_step_sec: float = 600.0
    stream_molecule_base_sec: float = 1800.0  # 蛋白获取 + 口袋预测 + 设计前置（各约 10 分钟）
    stream_per_molecule_sec: float = 600.0
    stream_max_sec: float = 7200.0  # 单轮最长 2 小时

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    class Config:
        env_file = ".env"


settings = Settings()
