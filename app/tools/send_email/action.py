import smtplib
from email.mime.text import MIMEText
from email.header import Header
import os
from langchain_core.tools import tool


@tool
def send_email(to_address: str, subject: str, content: str) -> str:
    """向指定的邮箱地址发送邮件。当用户明确要求发送邮件、通知或报告时使用。
    :param to_address: 收件人邮箱地址
    :param subject: 邮件主题
    :param content: 邮件正文
    """
    # 1. 从环境变量获取发件人账号（切勿写死在代码里）
    sender = os.getenv("SMTP_EMAIL")
    password = os.getenv("SMTP_PASSWORD")  # QQ邮箱这里要用授权码，不是登录密码

    if not sender or not password:
        return "发送失败：服务器未配置发件箱 SMTP_EMAIL 或 SMTP_PASSWORD。"

    # 2. 拦截非法注入（简易安全护栏）
    if "<script>" in content or "eval(" in content:
        return "发送被拦截：正文包含违规代码。"

    try:
        # 3. 组装邮件
        message = MIMEText(content, 'plain', 'utf-8')
        message['From'] = Header(f"AI 助手 <{sender}>", 'utf-8')
        message['To'] = Header(to_address, 'utf-8')
        message['Subject'] = Header(subject, 'utf-8')

        # 4. 连接 SMTP 服务器发信（以 QQ 邮箱为例）
        # 如果用的是 163 邮箱，就填 smtp.163.com
        server = smtplib.SMTP_SSL("smtp.qq.com", 465)
        server.login(sender, password)
        server.sendmail(sender, [to_address], message.as_string())
        server.quit()

        return f"✅ 成功发送邮件给 {to_address}！"
    except Exception as e:
        return f"邮件发送失败: {str(e)}"