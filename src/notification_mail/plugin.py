from __future__ import annotations

import html as html_lib
import mimetypes
import re
import smtplib
from email import encoders
from email.header import Header
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from app.plugins import PluginContext

from .schema import Config


EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
LOG_INLINE_LIMIT = 4000


class MailChannel:
    def __init__(self, ctx: "PluginContext", config: Config) -> None:
        self.ctx = ctx
        self.config = config

    async def send(self, payload: dict[str, Any]) -> bool:
        if not self.config.enabled:
            return False

        to_address = str(payload.get("to_address") or self.config.default_to_address).strip()
        mode = str(payload.get("mail_mode") or "网页")
        if mode == "网页":
            content = self._render_html_content(payload)
        else:
            content = self._render_text_content(payload)
        title = str(payload.get("title") or "AUTO-MAS 通知")
        self._validate(to_address)

        content = self._append_extra_to_content(content, mode, payload)
        attachments = self._build_extra_attachments(payload)
        message = self._build_message(mode, content, attachments)

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

        self.ctx.logger.info(f"邮件已发送: {title}")
        return True

    def _build_message(self, mode: str, content: str, attachments: list[MIMEBase]) -> MIMEMultipart | MIMEText:
        if attachments:
            message = MIMEMultipart("mixed")
            if mode == "网页":
                alternative = MIMEMultipart("alternative")
                alternative.attach(MIMEText(content, "html", "utf-8"))
                message.attach(alternative)
            else:
                message.attach(MIMEText(content, "plain", "utf-8"))
            for attachment in attachments:
                message.attach(attachment)
            return message

        if mode == "网页":
            message = MIMEMultipart("alternative")
            message.attach(MIMEText(content, "html", "utf-8"))
            return message
        return MIMEText(content, "plain", "utf-8")

    def _render_text_content(self, payload: dict[str, Any]) -> str:
        explicit = payload.get("mail_content")
        if explicit is not None:
            return str(explicit)

        text = str(payload.get("text") or "")
        signature = str(payload.get("signature") or "").strip()
        if signature:
            return f"{text}\n\n{signature}"
        return text

    def _render_html_content(self, payload: dict[str, Any]) -> str:
        explicit = payload.get("mail_content")
        if explicit is not None and str(payload.get("mail_mode") or "") == "网页":
            return str(explicit)

        title = str(payload.get("title") or "AUTO-MAS 通知")
        text = str(payload.get("text") or "")
        signature = str(payload.get("signature") or "").strip()
        data = payload.get("data")

        parts = [
            "<!doctype html>",
            "<html>",
            "<body>",
            f"<h2>{html_lib.escape(title)}</h2>",
            f"<p>{html_lib.escape(text).replace(chr(10), '<br>')}</p>",
        ]

        if isinstance(data, dict) and data:
            parts.append("<table border=\"1\" cellpadding=\"6\" cellspacing=\"0\">")
            for key, value in data.items():
                parts.append(
                    "<tr>"
                    f"<th align=\"left\">{html_lib.escape(str(key))}</th>"
                    f"<td>{html_lib.escape(str(value))}</td>"
                    "</tr>"
                )
            parts.append("</table>")

        if signature:
            parts.append(f"<p><small>{html_lib.escape(signature)}</small></p>")

        parts.extend(["</body>", "</html>"])
        return "\n".join(parts)

    def _append_extra_to_content(self, content: str, mode: str, payload: dict[str, Any]) -> str:
        extra_text = self._render_extra_text(payload, inline_long_logs=False)
        if not extra_text:
            return content
        if mode == "网页":
            return f"{content}<hr><pre>{html_lib.escape(extra_text)}</pre>"
        return f"{content}\n\n--- Extra ---\n{extra_text}"

    def _render_extra_text(self, payload: dict[str, Any], *, inline_long_logs: bool) -> str:
        extra = payload.get("extra")
        if not isinstance(extra, dict):
            return ""

        sections: list[str] = []
        logs = [item for item in extra.get("logs") or [] if isinstance(item, dict)]
        if logs:
            rendered_logs = []
            for index, item in enumerate(logs, start=1):
                name = str(item.get("name") or f"log-{index}.txt")
                level = str(item.get("level") or "info")
                content = str(item.get("content") or "")
                if not inline_long_logs and len(content) > LOG_INLINE_LIMIT:
                    rendered_logs.append(f"[{level}] {name}: attached as file")
                else:
                    rendered_logs.append(f"[{level}] {name}\n{content}")
            sections.append("Logs:\n" + "\n\n".join(rendered_logs))

        asset_lines = []
        for key, label in (("images", "Image"), ("attachments", "Attachment")):
            for index, item in enumerate(extra.get(key) or [], start=1):
                if not isinstance(item, dict):
                    continue
                name = str(item.get("caption") or item.get("name") or item.get("path") or f"{key}-{index}")
                path = str(item.get("path") or item.get("url") or "")
                asset_lines.append(f"{label}: {name}" + (f" ({path})" if path else ""))
        if asset_lines:
            sections.append("Assets:\n" + "\n".join(asset_lines))

        return "\n\n".join(section for section in sections if section).strip()

    def _build_extra_attachments(self, payload: dict[str, Any]) -> list[MIMEBase]:
        extra = payload.get("extra")
        if not isinstance(extra, dict):
            return []

        attachments: list[MIMEBase] = []
        for index, item in enumerate(extra.get("logs") or [], start=1):
            if not isinstance(item, dict):
                continue
            content = str(item.get("content") or "")
            if len(content) <= LOG_INLINE_LIMIT:
                continue
            name = str(item.get("name") or f"log-{index}.txt")
            attachments.append(self._text_attachment(name, content))

        for key in ("images", "attachments"):
            for item in extra.get(key) or []:
                if not isinstance(item, dict):
                    continue
                attachment = self._file_attachment(item)
                if attachment is not None:
                    attachments.append(attachment)

        return attachments

    def _text_attachment(self, name: str, content: str) -> MIMEBase:
        part = MIMEBase("text", "plain")
        part.set_payload(content.encode("utf-8"))
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=name)
        part.add_header("Content-Type", "text/plain; charset=utf-8")
        return part

    def _file_attachment(self, item: dict[str, Any]) -> MIMEBase | None:
        raw_path = str(item.get("path") or "").strip()
        if not raw_path:
            return None
        path = Path(raw_path)
        if not path.exists() or not path.is_file():
            self.ctx.logger.warning(f"extra attachment missing: {raw_path}")
            return None

        name = str(item.get("name") or path.name)
        mime = str(item.get("mime") or mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        maintype, _, subtype = mime.partition("/")
        if not maintype or not subtype:
            maintype, subtype = "application", "octet-stream"

        part = MIMEBase(maintype, subtype)
        part.set_payload(path.read_bytes())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=name)
        return part

    def _validate(self, to_address: str) -> None:
        if not self.config.smtp_server:
            raise ValueError("SMTP 服务地址不能为空")
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
        self.ctx.logger.info("通道已启动")

    async def on_stop(self, reason: str) -> None:
        notify = self.ctx.get("notify")
        if notify is not None:
            notify.unregister_channel("mail")
        self.ctx.logger.info(f"插件停止, reason={reason}")
