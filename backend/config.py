from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openclaw_base_url: str = "http://127.0.0.1:18789"
    openclaw_api_key: str = "a5c48bbab43af2819dd167088ca27a84bd6d3ff5ac81304e"
    openclaw_agent_id: str = "main"
    openclaw_model: str = "openclaw:main"
    openclaw_system_prompt: str = (
        "你是猛犸智能体助手。"
        "在任何可用的情况下，必须先优先匹配并调用 OpenClaw 已安装的技能/工具完成任务，再用工具结果回答。"
        "语言硬性要求：对用户回答、分析过程、以及内部 thinking/推理过程一律使用简体中文；"
        "禁止用英文写思考过程。工具名、路径、命令、代码、SMILES 等可保留原文，说明文字必须中文。"
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
    openclaw_sessions_index: str = "/home/dbcloud/.openclaw/agents/main/sessions/sessions.json"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    class Config:
        env_file = ".env"


settings = Settings()
