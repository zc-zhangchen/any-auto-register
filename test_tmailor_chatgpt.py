#!/usr/bin/env python3
"""测试 Tmailor 接收 ChatGPT 验证码邮件"""

import time
from core.tmailor_mailbox import TmailorMailbox

def test_tmailor_receive():
    mb = TmailorMailbox()
    acc = mb.get_email()
    email = acc.email
    token = acc.account_id

    print(f"\n生成的邮箱: {email}")
    print(f"Token: {token}")
    print("\n请手动访问 ChatGPT 注册页面,使用这个邮箱注册,然后等待邮件...\n")
    print("或者你可以用任何方式给这个邮箱发送一封主题包含验证码的邮件\n")

    # 等待邮件
    print("开始轮询邮件 (120秒)...")
    end = time.time() + 120
    list_id = None
    check_count = 0

    while time.time() < end:
        check_count += 1
        list_id, messages = mb._list_inbox(token, list_id)

        print(f"\n第 {check_count} 次检查: 收到 {len(messages)} 封邮件")

        if messages:
            for i, msg in enumerate(messages, 1):
                print(f"\n邮件 {i}:")
                print(f"  ID: {msg.get('id')}")
                print(f"  主题: {msg.get('subject')}")
                print(f"  发件人: {msg.get('from')}")
                print(f"  预览: {msg.get('text', '')[:100]}")

                # 读取详情
                detail = mb._read_mail_detail(token, msg)
                if detail:
                    print(f"\n  详细内容:")
                    print(f"    主题: {detail.get('subject')}")
                    print(f"    正文预览: {detail.get('body', '')[:300]}")
                    print(f"    text字段: {detail.get('text', '')[:300]}")

                    # 测试匹配逻辑
                    is_openai = mb._is_openai_mail(msg, detail)
                    print(f"\n  是否匹配 OpenAI: {is_openai}")

                    if is_openai:
                        code = mb._extract_code_from_mail(msg, detail)
                        print(f"  提取的验证码: {code}")

        time.sleep(5)

    print("\n测试结束")

if __name__ == "__main__":
    test_tmailor_receive()
