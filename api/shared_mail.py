"""隐私邮箱最新邮件的免登录页面。

这条路由刻意不挂在 /api 下：main 的鉴权中间件只拦 /api/*，这里要的就是
把链接复制给别人、对方不登录面板也能打开。链接本身就是权限，凭证是别名行上
那串 128 位随机 share_token，不是自增 id——用 id 谁都能从 1 数到 100。
"""

from __future__ import annotations

import html
import logging
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from platforms.icloud import ICloudError
from platforms.icloud.models import MailMessage
from services import icloud_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["shared-mail"])

# 页面配色跟面板暗色主题同一套值
_PAGE_STYLE = """
  :root{color-scheme:dark;}
  *{box-sizing:border-box;}
  body{margin:0;padding:24px 16px;background:#161922;color:#d7dce5;
    font:14px/1.7 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;}
  .card{max-width:860px;margin:0 auto;background:#1e212c;border:1px solid rgba(255,255,255,.09);
    border-radius:12px;overflow:hidden;box-shadow:0 12px 40px rgba(0,0,0,.32);}
  .head{padding:20px 24px;border-bottom:1px solid rgba(255,255,255,.09);}
  .subject{margin:0 0 10px;font-size:18px;font-weight:600;word-break:break-word;}
  .meta{color:#a4adbd;font-size:13px;word-break:break-word;}
  .meta span{color:#7b8595;}
  .body{padding:0;background:#f7f8fa;}
  iframe{display:block;width:100%;border:0;background:#f7f8fa;}
  .text{padding:20px 24px;white-space:pre-wrap;word-break:break-word;color:#c3cad6;}
  .foot{display:flex;justify-content:space-between;gap:12px;align-items:center;
    padding:14px 24px;border-top:1px solid rgba(255,255,255,.09);color:#7b8595;font-size:12px;}
  a.button{color:#5f82b8;text-decoration:none;border:1px solid rgba(95,130,184,.4);
    border-radius:8px;padding:6px 14px;background:rgba(95,130,184,.16);}
  a.button:hover{color:#7396c8;}
  .empty{padding:48px 24px;text-align:center;color:#7b8595;}
"""

# 邮件正文是别人写的 HTML，塞进不给脚本的 iframe 里渲染
_BODY_STYLE = (
    "html,body{margin:0;padding:16px;background:#f7f8fa;color:#2f3540;"
    'font:14px/1.7 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,'
    '"Helvetica Neue",Arial,sans-serif;word-break:break-word;overflow-wrap:anywhere;}'
    "img,table{max-width:100%!important;height:auto;}"
    "a{color:#3f6ea8;}"
)


def _page(title: str, inner: str, *, status_code: int = 200) -> HTMLResponse:
    return HTMLResponse(
        f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>{html.escape(title)}</title>
<style>{_PAGE_STYLE}</style></head>
<body><div class="card">{inner}</div></body></html>""",
        status_code=status_code,
        # 链接会被转发，别让中间层缓存别人的邮件
        headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow"},
    )


def _body_frame(message: MailMessage) -> str:
    body_html = (message.html_body or "").strip()
    if body_html:
        srcdoc = html.escape(
            f'<!doctype html><html><head><meta charset="utf-8">'
            f'<meta http-equiv="Content-Security-Policy" content="script-src \'none\'">'
            f"<style>{_BODY_STYLE}</style></head><body>{body_html}</body></html>",
            quote=True,
        )
        # 不给 allow-scripts，框里的 HTML 只能当静态内容渲染；
        # allow-same-origin 是为了外层量高度，脚本被禁用后框内拿不到任何东西
        return (
            f'<iframe title="邮件正文" sandbox="allow-same-origin" '
            f'srcdoc="{srcdoc}" onload="fit(this)" style="height:320px"></iframe>'
            "<script>function fit(f){function m(){try{"
            "f.style.height=(f.contentDocument.body.scrollHeight+32)+'px';"
            "}catch(e){}}m();setTimeout(m,300);}</script>"
        )

    text = (message.text_body or message.snippet or "").strip()
    if not text:
        return '<div class="empty">这封邮件没有正文</div>'
    return f'<div class="text">{html.escape(text)}</div>'


def _sender(message: MailMessage) -> str:
    name = (message.sender.name or "").strip()
    email = (message.sender.email or "").strip()
    if name and email:
        return f"{html.escape(name)} <span>&lt;{html.escape(email)}&gt;</span>"
    return html.escape(name or email or "未知发件人")


def _received_at(message: MailMessage) -> str:
    value = getattr(message, "received_at", None)
    if not value:
        return ""
    try:
        return value.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except (AttributeError, ValueError):
        return str(value)


def _render_message(address: str, message: Optional[MailMessage]) -> HTMLResponse:
    safe_address = html.escape(address)
    if message is None:
        inner = (
            f'<div class="head"><h1 class="subject">还没有邮件</h1>'
            f'<div class="meta">{safe_address}</div></div>'
            '<div class="empty">这个隐私邮箱暂时没收到邮件，收到后刷新本页即可看到。</div>'
            '<div class="foot"><span>只显示最新一封</span>'
            '<a class="button" href="">刷新</a></div>'
        )
        return _page(f"{address} · 最新邮件", inner)

    subject = html.escape((message.subject or "").strip() or "(无主题)")
    received = html.escape(_received_at(message))
    inner = (
        f'<div class="head"><h1 class="subject">{subject}</h1>'
        f'<div class="meta">{_sender(message)}</div>'
        f'<div class="meta"><span>发往</span> {safe_address}'
        f'{" · " + received if received else ""}</div></div>'
        f'<div class="body">{_body_frame(message)}</div>'
        '<div class="foot"><span>只显示最新一封，收到新邮件后刷新即可</span>'
        '<a class="button" href="">刷新</a></div>'
    )
    return _page(f"{subject} · {address}", inner)


def _error_page(title: str, detail: str, *, status_code: int) -> HTMLResponse:
    inner = (
        f'<div class="head"><h1 class="subject">{html.escape(title)}</h1></div>'
        f'<div class="empty">{html.escape(detail)}</div>'
    )
    return _page(title, inner, status_code=status_code)


@router.get("/m/{share_token}", response_class=HTMLResponse, include_in_schema=False)
def shared_latest_mail(share_token: str) -> HTMLResponse:
    try:
        address, message = icloud_service.fetch_latest_shared_message(share_token)
    except ICloudError as error:
        if error.code == "alias_not_found":
            return _error_page("链接无效", "这个邮件链接不存在或已被删除。", status_code=404)
        logger.warning("免登录取信失败 [%s]: %s", error.code, error)
        return _error_page("暂时读不到邮件", str(error), status_code=502)
    except Exception:  # noqa: BLE001 - 免登录页面不能把栈打给外面
        logger.exception("免登录取信异常")
        return _error_page("暂时读不到邮件", "服务异常，请稍后再试。", status_code=500)
    return _render_message(address, message)
