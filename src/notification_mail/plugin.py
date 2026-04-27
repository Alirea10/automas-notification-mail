from __future__ import annotations

import re
import smtplib
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from mas.plugins import PluginContext

from .schema import Config


EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


class MailChannel:
    def __init__(self, ctx: "PluginContext", config: Config) -> None:
        self.ctx = ctx
        self.config = config

    async def send(self, payload: dict[str, Any]) -> bool:
        if not self.config.enabled:
            return False

        to_address = str(payload.get("to_address") or self.config.default_to_address).strip()
        mode = str(payload.get("mail_mode") or ("网页" if payload.get("html") else "文本"))
        content = str(payload.get("html") if mode == "网页" else payload.get("text") or "")
        title = str(payload.get("title") or "AUTO-MAS 通知")
        self._validate(to_address)

        if mode == "网页":
            message = MIMEMultipart("alternative")
            message.attach(MIMEText(content, "html", "utf-8"))
        else:
            message = MIMEText(content, "plain", "utf-8")

        message["From"] = formataddr((Header(self.config.sender_name, "utf-8").encode(), self.config.from_address))
        message["To"] = formataddr((Header(self.config.receiver_name, "utf-8").encode(), to_address))
        message["Subject"] = str(Header(title, "utf-8"))

        if self.config.use_ssl:
            smtp = smtplib.SMTP_SSL(self.config.smtp_server, self.config.smtp_port)
        else:
            smtp = smtplib.SMTP(self.config.smtp_server, self.config.smtp_port)
        try:
            smtp.login(self.config.from_address, self.config.authorization_code)
            smtp.sendmail(self.config.from_address, to_address, message.as_string())
        finally:
            smtp.quit()

        self.ctx.logger.info(f"[notification_mail] 邮件已发送: {title}")
        return True

    def _validate(self, to_address: str) -> None:
        if not self.config.smtp_server:
            raise ValueError("SMTP 服务器地址不能为空")
        if not self.config.authorization_code:
            raise ValueError("邮件授权码不能为空")
        if not EMAIL_RE.match(self.config.from_address):
            raise ValueError("发件邮箱格式错误或为空")
        if not EMAIL_RE.match(to_address):
            raise ValueError("收件邮箱格式错误或为空")


class Plugin:
    needs = "notify"

    def __init__(self, ctx: "PluginContext") -> None:
        self.ctx = ctx

    async def on_start(self) -> None:
        raw_config = self.ctx.config.to_dict() if hasattr(self.ctx.config, "to_dict") else dict(self.ctx.config)
        channel = MailChannel(self.ctx, Config.model_validate(raw_config))
        self.ctx.get("notify").register_channel("mail", channel)
        self.ctx.logger.info("[notification_mail] 通道已启动")

    async def on_stop(self, reason: str) -> None:
        notify = self.ctx.get("notify")
        if notify is not None:
            notify.unregister_channel("mail")
        self.ctx.logger.info(f"[notification_mail] 插件停止, reason={reason}")
