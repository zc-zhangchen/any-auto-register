const axios = require('axios');

/**
 * 邮箱验证码获取服务
 * 支持 Cloudflare Temp Email (dreamhunter2333) 和 cfworker 两种后端
 */
class MailService {
    /**
     * @param {string} mailInboxUrl - 带 JWT 的自动登录链接
     */
    constructor(mailInboxUrl) {
        this.mailInboxUrl = mailInboxUrl;

        // 从 URL 中解析 base URL 和 JWT
        const parsed = new URL(mailInboxUrl);
        this.baseUrl = `${parsed.protocol}//${parsed.host}`;
        this.jwt = parsed.searchParams.get('jwt') || '';

        if (!this.jwt) {
            throw new Error('mailInboxUrl 中未找到 jwt 参数');
        }

        console.log(`[邮箱] 初始化邮箱服务: ${this.baseUrl}`);
    }

    /**
     * 获取邮件列表
     * @param {number} limit 
     * @returns {Promise<Array>}
     */
    async fetchMails(limit = 5) {
        try {
            const resp = await axios.get(`${this.baseUrl}/api/mails`, {
                params: { limit, offset: 0 },
                headers: {
                    'Authorization': `Bearer ${this.jwt}`,
                    'Accept': 'application/json',
                },
                timeout: 15000,
            });

            if (resp.status !== 200) return [];

            const payload = resp.data;
            if (typeof payload === 'object' && !Array.isArray(payload)) {
                // cloudflare_temp_email 格式: { results: [...], count: number }
                // 或 cfworker 格式: { mails: [...] }
                return payload.results || payload.mails || [];
            }
            if (Array.isArray(payload)) {
                return payload;
            }
            return [];
        } catch (error) {
            if (error.response && error.response.status === 401) {
                console.error('[邮箱] JWT Token 无效或已过期');
            }
            return [];
        }
    }

    /**
     * 从邮件内容中提取 6 位验证码
     * @param {string} content 
     * @returns {string|null}
     */
    extractCode(content) {
        if (!content) return null;

        const patterns = [
            // HTML 邮件中常见格式
            /background-color:\s*#F3F3F3[^>]*>[\s\S]*?(\d{6})[\s\S]*?<\/p>/i,
            // Subject 中的验证码
            /Subject:.*?(\d{6})/i,
            // 常见文本格式
            /Your (?:ChatGPT )?code is\s*(\d{6})/i,
            /verification code[:\s]*(\d{6})/i,
            /verify your email[:\s]*(\d{6})/i,
            /temporary verification code to continue:\s*(\d{6})/i,
            // HTML 标签内
            />\s*(\d{6})\s*</,
            // 通用 6 位数字 (排除常见非验证码数字)
            /(?<![#&])\b(\d{6})\b/,
        ];

        for (const pattern of patterns) {
            const match = content.match(pattern);
            if (match && match[1] !== '177010') {
                return match[1];
            }
        }
        return null;
    }

    /**
     * 判断邮件是否来自 OpenAI
     * @param {object} mail 
     * @returns {boolean}
     */
    isOpenAIMail(mail) {
        const raw = String(mail.raw || '').toLowerCase();
        const subject = String(mail.subject || '').toLowerCase();
        const sender = typeof mail.from === 'object'
            ? String(mail.from.address || '').toLowerCase()
            : String(mail.from || '').toLowerCase();

        return (
            sender.includes('openai') ||
            subject.includes('chatgpt') ||
            subject.includes('verify') ||
            raw.includes('noreply@openai') ||
            raw.includes('openai')
        );
    }

    /**
     * 从单封邮件中提取验证码
     * @param {object} mail 
     * @returns {string|null}
     */
    extractCodeFromMail(mail) {
        const candidates = [
            String(mail.verification_code || ''),
            String(mail.raw || ''),
            String(mail.subject || ''),
            String(mail.text || ''),
            String(mail.body || ''),
            String(mail.html || ''),
            String(mail.snippet || ''),
            String(mail.content || ''),
        ];

        for (const text of candidates) {
            const code = this.extractCode(text);
            if (code) return code;
        }
        return null;
    }

    /**
     * 轮询等待验证码
     * @param {object} options
     * @param {number} options.timeout - 超时时间（秒）
     * @param {number} options.pollInterval - 轮询间隔（秒）
     * @param {number} options.notBeforeTs - 忽略此时间戳之前的邮件
     * @returns {Promise<string|null>}
     */
    async waitForCode({ timeout = 120, pollInterval = 3, notBeforeTs = null } = {}) {
        const startTime = Date.now();
        const timeoutMs = timeout * 1000;

        console.log(`[邮箱] 开始轮询验证码，超时 ${timeout}s，间隔 ${pollInterval}s`);

        while (Date.now() - startTime < timeoutMs) {
            try {
                const mails = await this.fetchMails(5);
                
                for (const mail of mails) {
                    // 检查时间
                    if (notBeforeTs) {
                        const createdAt = mail.created_at || mail.createdAt;
                        if (createdAt) {
                            const mailTs = new Date(createdAt).getTime() / 1000;
                            if (mailTs < notBeforeTs - 2) continue;
                        }
                    }

                    // 检查是否是 OpenAI 的邮件
                    if (!this.isOpenAIMail(mail)) continue;

                    // 提取验证码
                    const code = this.extractCodeFromMail(mail);
                    if (code) {
                        console.log(`[邮箱] 成功获取验证码: ${code}`);
                        return code;
                    }
                }
            } catch (error) {
                console.error(`[邮箱] 轮询出错: ${error.message}`);
            }

            // 等待下一次轮询
            await new Promise(resolve => setTimeout(resolve, pollInterval * 1000));
        }

        console.error('[邮箱] 验证码获取超时');
        return null;
    }
}

module.exports = { MailService };
