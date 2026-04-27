from pydantic import BaseModel, ConfigDict, Field


class Config(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = Field(default=True, description="启用邮件通知")
    smtp_server: str = Field(default="", description="SMTP 服务器地址")
    smtp_port: int = Field(default=465, ge=1, description="SMTP 端口")
    use_ssl: bool = Field(default=True, description="使用 SSL")
    from_address: str = Field(default="", description="发件邮箱")
    authorization_code: str = Field(
        default="",
        description="授权码/密码",
        json_schema_extra={"format": "password"},
    )
    default_to_address: str = Field(default="", description="默认收件邮箱")
    sender_name: str = Field(default="AUTO-MAS通知服务", description="发件人名称")
    receiver_name: str = Field(default="AUTO-MAS用户", description="收件人名称")
