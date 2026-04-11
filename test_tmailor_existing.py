#!/usr/bin/env python3
"""测试 Tmailor 邮件获取"""

import time
from core.tmailor_mailbox import TmailorMailbox
from core.base_mailbox import MailboxAccount

def test_existing_mailbox():
    """测试之前说有邮件的邮箱"""
    token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJlIjoicHprS1pUOGxNM3lpTEhIMXBTRVZxeFcySTN5aUZ5QXdvMU9KTXlNNkZKcVpGYXl6Rm1XR3BSMUlJM3lqWjFjMkRhTUtueGtZRUprT0ZhSWJveGNXR3hqbEJKdWtJU0EzbzJqMW5LTzZwVU1NSFNwbUdIY0tuUmtYWkt5WVp4SWNvMGNHTDI5Mkl3TUpMSElhR1JjNU16OG1JenVaWnd5YUlhTWRxeDFIRkdXaEZ4UzVJYXF2cWFSbEZLTUpxemMyR0hia3FKNVhuMnVBRjNTbW94Y1JxeFczSHdJT0hLRGxKeVNaWjBTRG5hTWtGMFM1cFV4NUwwMURJd01uSUdSNHBUMTRBUldZSncwPSJ9.6s_KoEPfHWtNzTMqUXDGDNgZIz6332h102kaBSDjoQ0"
    email = "patr5hnie@contaco.org"

    mb = TmailorMailbox()
    print(f"检查邮箱: {email}")
    print(f"Token: {token}")
    print("\n访问方式: 打开 https://tmailor.com 输入上面的 token\n")

    # 测试 API 调用
    list_id, messages = mb._list_inbox(token)
    print(f"\n收到 {len(messages)} 封邮件")

    if messages:
        for i, msg in enumerate(messages, 1):
            print(f"\n邮件 {i}:")
            print(f"  ID: {msg.get('id')}")
            print(f"  主题: {msg.get('subject')}")

            # 读取详情
            detail = mb._read_mail_detail(token, msg)
            if detail:
                print(f"  详细主题: {detail.get('subject')}")
                print(f"  详细正文前300字: {detail.get('body', '')[:300]}")

                # 测试匹配
                is_openai = mb._is_openai_mail(msg, detail)
                print(f"  是否匹配 OpenAI: {is_openai}")

                if is_openai:
                    code = mb._extract_code_from_mail(msg, detail)
                    print(f"  提取的验证码: {code}")
    else:
        print("\n没有邮件,可能原因:")
        print("1. Token 已过期")
        print("2. 邮件已被删除")
        print("3. API 参数不对")

if __name__ == "__main__":
    test_existing_mailbox()
