from app.core.plugins.fields import PluginField
from pydantic import BaseModel, ConfigDict


class Config(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = PluginField(default=True, description="启用邮件通知")
    smtp_server: str = PluginField(default="", description="SMTP 服务器地址")
    smtp_port: int = PluginField(default=465, ge=1, description="SMTP 端口")
    use_ssl: bool = PluginField(default=True, description="使用 SSL")
    from_address: str = PluginField(default="", description="发件邮箱")
    authorization_code: str = PluginField(
        default="",
        description="授权码/密码",
        format="password",
    )
    default_to_address: str = PluginField(default="", description="默认收件邮箱")
    sender_name: str = PluginField(default="AUTO-MAS通知服务", description="发件人名称")
    receiver_name: str = PluginField(default="AUTO-MAS用户", description="收件人名称")
