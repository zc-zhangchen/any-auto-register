#!/usr/bin/env python3
"""测试修复后的 Tmailor 邮件获取"""

import time
from core.tmailor_mailbox import TmailorMailbox
from core.base_mailbox import MailboxAccount

def test_tmailor_fixed():
    print("=" * 60)
    print("测试修复后的 Tmailor 邮件获取")
    print("=" * 60)

    mb = TmailorMailbox()

    # 创建邮箱
    print("\n1. 创建邮箱...")
    acc = mb.get_email()
    print(f"邮箱: {acc.email}")
    print(f"Token: {acc.account_id}")
    print(f"\n访问方式: 打开 https://tmailor.com 输入上面的 token")

    # 等待 10 秒,让用户有时间发送测试邮件
    print("\n2. 等待 10 秒,请手动给这个邮箱发送测试邮件...")
    time.sleep(10)

    # 测试 API 调用
    print("\n3. 测试 listinbox API...")
    token = acc.account_id
    list_id, messages = mb._list_inbox(token)
    print(f"收到 {len(messages)} 封邮件")

    if messages:
        print("\n✅ 成功! API 返回了邮件数据")
        for i, msg in enumerate(messages, 1):
            print(f"\n邮件 {i}:")
            print(f"  ID: {msg.get('id')}")
            print(f"  主题: {msg.get('subject')}")
            print(f"  发件人: {msg.get('sender_email')}")

            # 测试匹配和提取
            detail = mb._read_mail_detail(token, msg)
            if detail:
                is_openai = mb._is_openai_mail(msg, detail)
                print(f"  是否匹配 OpenAI: {is_openai}")

                if is_openai:
                    code = mb._extract_code_from_mail(msg, detail)
                    print(f"  提取的验证码: {code}")
    else:
        print("\n❌ 失败: API 仍然返回空数据")
        print("可能原因:")
        print("1. 还没有邮件发送到这个邮箱")
        print("2. Cloudflare 验证仍然有问题")
        print("3. 需要其他 headers 或 cookies")

    # 测试 wait_for_code (30秒超时)
    print("\n4. 测试 wait_for_code (30秒超时)...")
    print("如果之前没有邮件,请现在发送测试邮件")
    try:
        code = mb.wait_for_code(acc, timeout=30)
        print(f"\n✅ 成功获取验证码: {code}")
    except TimeoutError as e:
        print(f"\n⏱️ 超时: {e}")
    except Exception as e:
        print(f"\n❌ 错误: {e}")

if __name__ == "__main__":
    test_tmailor_fixed()
