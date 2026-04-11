const axios = require('axios');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const { buildSentinelToken, USER_AGENT } = require('./sentinelService');

const OPENAI_AUTH_BASE = 'https://auth.openai.com';

const COMMON_HEADERS = {
    'accept': 'application/json',
    'accept-language': 'en-US,en;q=0.9',
    'content-type': 'application/json',
    'origin': OPENAI_AUTH_BASE,
    'user-agent': USER_AGENT,
    'sec-ch-ua': '"Google Chrome";v="145", "Not?A_Brand";v="8", "Chromium";v="145"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
};

const NAVIGATE_HEADERS = {
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'accept-language': 'en-US,en;q=0.9',
    'user-agent': USER_AGENT,
    'sec-ch-ua': '"Google Chrome";v="145", "Not?A_Brand";v="8", "Chromium";v="145"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'document',
    'sec-fetch-mode': 'navigate',
    'sec-fetch-site': 'same-origin',
    'sec-fetch-user': '?1',
    'upgrade-insecure-requests': '1',
};

class OAuthService {
    constructor() {
        this.clientId = 'app_EMoamEEZ73f0CkXaXp7hrann';
        this.redirectPort = 1455;
        this.redirectUri = `http://localhost:${this.redirectPort}/auth/callback`;
        this.codeVerifier = null;
        this.codeChallenge = null;
        this.state = null;
        this.regeneratePKCE();
    }

    generateCodeVerifier() {
        return crypto.randomBytes(32).toString('base64url');
    }

    generateCodeChallenge(verifier) {
        return crypto.createHash('sha256').update(verifier).digest('base64url');
    }

    regeneratePKCE() {
        this.codeVerifier = this.generateCodeVerifier();
        this.codeChallenge = this.generateCodeChallenge(this.codeVerifier);
        this.state = crypto.randomBytes(16).toString('hex');
        console.log('[OAuth] 已重新生成 PKCE 参数和 state');
    }

    getAuthUrl() {
        const params = new URLSearchParams({
            client_id: this.clientId,
            code_challenge: this.codeChallenge,
            code_challenge_method: 'S256',
            codex_cli_simplified_flow: 'true',
            id_token_add_organizations: 'true',
            prompt: 'login',
            redirect_uri: this.redirectUri,
            response_type: 'code',
            scope: 'openid email profile offline_access',
            state: this.state
        });
        return `${OPENAI_AUTH_BASE}/oauth/authorize?${params.toString()}`;
    }

    extractCallbackParams(callbackUrl) {
        try {
            const url = new URL(callbackUrl);
            const params = {
                code: url.searchParams.get('code'),
                state: url.searchParams.get('state'),
                error: url.searchParams.get('error'),
                error_description: url.searchParams.get('error_description')
            };
            if (params.state && params.state !== this.state) {
                console.error('[OAuth] State 不匹配:', params.state, '期望:', this.state);
                return null;
            }
            return params;
        } catch (e) {
            console.error('[OAuth] 解析回调 URL 失败:', e.message);
            return null;
        }
    }

    /**
     * 纯协议 OAuth 授权流程
     * @param {string} email 
     * @param {string} password 
     * @param {function} waitForCode - 等待验证码的函数
     * @returns {Promise<{success: boolean, code?: string, reason?: string}>}
     */
    async protocolOAuth(email, password, waitForCode) {
        console.log('[OAuth] 开始纯协议 OAuth 授权流程');

        const cookies = {};
        const deviceId = crypto.randomUUID();
        cookies['oai-did'] = deviceId;

        // 手动重定向跟随请求方法
        const request = async (method, url, options = {}) => {
            const { headers = {}, data = null, maxRedirects = 10 } = options;
            let currentUrl = url;
            let redirectCount = 0;

            while (true) {
                const cookieStr = Object.entries(cookies).map(([k, v]) => `${k}=${v}`).join('; ');
                const reqHeaders = { ...headers, Cookie: cookieStr };

                const config = {
                    method: redirectCount === 0 ? method : 'GET',
                    url: currentUrl,
                    headers: reqHeaders,
                    maxRedirects: 0,
                    validateStatus: () => true,
                    timeout: 30000,
                };
                if (redirectCount === 0 && data !== null && data !== undefined) {
                    config.data = data;
                }

                const resp = await axios(config);

                // 收集 cookies
                const setCookies = resp.headers['set-cookie'];
                if (setCookies) {
                    for (const cs of setCookies) {
                        const [nv] = cs.split(';');
                        const eqIdx = nv.indexOf('=');
                        if (eqIdx > 0) {
                            cookies[nv.substring(0, eqIdx).trim()] = nv.substring(eqIdx + 1).trim();
                        }
                    }
                }

                if (resp.status >= 300 && resp.status < 400 && resp.headers['location']) {
                    redirectCount++;
                    if (redirectCount > maxRedirects) return resp;
                    const location = resp.headers['location'];
                    try { currentUrl = new URL(location, currentUrl).toString(); } catch { currentUrl = location; }
                    try {
                        const parsedRedirect = new URL(currentUrl);
                        if (parsedRedirect.hostname === 'localhost') {
                            return { ...resp, _redirectedToLocalhost: true, _finalUrl: currentUrl };
                        }
                    } catch {}
                    continue;
                }
                return resp;
            }
        };

        // Step 1: 初始化 OAuth
        this.regeneratePKCE();
        const authUrl = this.getAuthUrl();
        console.log('[OAuth] Step 1: 初始化 OAuth 会话');

        try {
            await request('GET', authUrl, { headers: NAVIGATE_HEADERS });
        } catch (error) {
            return { success: false, reason: `oauth_init_failed:${error.message}` };
        }

        // Step 2: 提交登录邮箱
        console.log('[OAuth] Step 2: 提交登录邮箱');
        const sentinelToken = await buildSentinelToken(deviceId, 'authorize_continue');
        if (!sentinelToken) {
            return { success: false, reason: 'sentinel_token_failed' };
        }

        const loginHeaders = {
            ...COMMON_HEADERS,
            'referer': `${OPENAI_AUTH_BASE}/login`,
            'oai-device-id': deviceId,
            'openai-sentinel-token': sentinelToken,
        };

        try {
            const resp = await request('POST',
                `${OPENAI_AUTH_BASE}/api/accounts/authorize/continue`,
                { data: { username: { kind: 'email', value: email }, screen_hint: 'login' }, headers: loginHeaders }
            );
            if (resp.status !== 200) {
                return { success: false, reason: `oauth_login_email_http_${resp.status}` };
            }
        } catch (error) {
            return { success: false, reason: `oauth_login_email_failed:${error.message}` };
        }

        // Step 3: 提交密码
        console.log('[OAuth] Step 3: 提交密码');
        const pwdSentinelToken = await buildSentinelToken(deviceId, 'authorize_continue');
        const pwdHeaders = {
            ...COMMON_HEADERS,
            'referer': `${OPENAI_AUTH_BASE}/login/password`,
            'oai-device-id': deviceId,
            'openai-sentinel-token': pwdSentinelToken || '',
        };

        try {
            const resp = await request('POST',
                `${OPENAI_AUTH_BASE}/api/accounts/authorize/continue`,
                { data: { password }, headers: pwdHeaders }
            );

            if (resp._redirectedToLocalhost && resp._finalUrl) {
                try {
                    const parsed = new URL(resp._finalUrl);
                    const code = parsed.searchParams.get('code');
                    if (code) {
                        console.log('[OAuth] 密码登录后直接获取到 code');
                        return { success: true, code };
                    }
                } catch {}
            }

            if (resp.status === 200 && resp.data && typeof resp.data === 'object') {
                for (const key of ['continue_url', 'callback_url', 'url', 'redirect_url']) {
                    const url = resp.data[key];
                    if (url && typeof url === 'string' && url.includes('code=')) {
                        try {
                            const parsed = new URL(url);
                            const code = parsed.searchParams.get('code');
                            if (code) {
                                console.log('[OAuth] 密码登录响应中获取到 code');
                                return { success: true, code };
                            }
                        } catch {}
                    }
                }
            }

            if (resp.status !== 200) {
                return { success: false, reason: `oauth_login_pwd_http_${resp.status}` };
            }
        } catch (error) {
            return { success: false, reason: `oauth_login_pwd_failed:${error.message}` };
        }

        // Step 4: 可能需要 OTP
        console.log('[OAuth] Step 4: 检查是否需要 OTP...');
        const otpRequestedAt = Date.now() / 1000;

        try {
            const sendResp = await request('GET',
                `${OPENAI_AUTH_BASE}/api/accounts/email-otp/send`,
                { headers: { ...NAVIGATE_HEADERS, referer: `${OPENAI_AUTH_BASE}/login/password` } }
            );
            if ([200, 204, 301, 302].includes(sendResp.status)) {
                console.log('[OAuth] OTP 已发送，等待验证码...');

                const code = await waitForCode(otpRequestedAt);
                if (!code) {
                    return { success: false, reason: 'oauth_otp_timeout' };
                }

                const otpHeaders = {
                    ...COMMON_HEADERS,
                    'referer': `${OPENAI_AUTH_BASE}/email-verification`,
                    'oai-device-id': deviceId,
                };
                const otpResp = await request('POST',
                    `${OPENAI_AUTH_BASE}/api/accounts/email-otp/validate`,
                    { data: { code }, headers: otpHeaders }
                );

                if (otpResp._redirectedToLocalhost && otpResp._finalUrl) {
                    try {
                        const parsed = new URL(otpResp._finalUrl);
                        const authCode = parsed.searchParams.get('code');
                        if (authCode) return { success: true, code: authCode };
                    } catch {}
                }

                if (otpResp.status === 200 && otpResp.data && typeof otpResp.data === 'object') {
                    for (const key of ['continue_url', 'callback_url', 'url', 'redirect_url']) {
                        const url = otpResp.data[key];
                        if (url && typeof url === 'string' && url.includes('code=')) {
                            try {
                                const parsed = new URL(url);
                                const authCode = parsed.searchParams.get('code');
                                if (authCode) return { success: true, code: authCode };
                            } catch {}
                        }
                    }
                }
            }
        } catch (error) {
            // OTP 可能不需要
        }

        // Step 5: 尝试 consent 获取 code
        console.log('[OAuth] Step 5: 尝试通过 consent 获取 code');
        try {
            const consentResp = await request('GET',
                `${OPENAI_AUTH_BASE}/sign-in-with-chatgpt/codex/consent`,
                { headers: NAVIGATE_HEADERS }
            );

            if (consentResp._redirectedToLocalhost && consentResp._finalUrl) {
                try {
                    const parsed = new URL(consentResp._finalUrl);
                    const code = parsed.searchParams.get('code');
                    if (code) {
                        console.log('[OAuth] 从 consent 重定向获取到 code');
                        return { success: true, code };
                    }
                } catch {}
            }
        } catch (error) {
            console.error('[OAuth] consent 请求失败:', error.message);
        }

        return { success: false, reason: 'oauth_code_not_found_after_all_attempts' };
    }

    /**
     * 用授权码换取 Token
     */
    async exchangeTokenAndSave(code, email) {
        try {
            console.log('[OAuth] 开始用 code 换取 Token');

            const body = new URLSearchParams({
                grant_type: 'authorization_code',
                code: code,
                redirect_uri: this.redirectUri,
                client_id: this.clientId,
                code_verifier: this.codeVerifier
            }).toString();

            const response = await axios.post(`${OPENAI_AUTH_BASE}/oauth/token`, body, {
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
            });

            const tokens = response.data;

            let accountId = '';
            try {
                const payloadStr = Buffer.from(tokens.access_token.split('.')[1], 'base64').toString('utf8');
                const payload = JSON.parse(payloadStr);
                const apiAuth = payload['https://api.openai.com/auth'] || {};
                accountId = apiAuth.chatgpt_account_id || '';
            } catch (e) {
                console.error('[OAuth] 解析 access_token 获取 account_id 失败:', e.message);
            }

            const now = new Date();
            const expiredTime = new Date(now.getTime() + tokens.expires_in * 1000);

            const outData = {
                access_token: tokens.access_token,
                account_id: accountId,
                disabled: false,
                email: email,
                expired: expiredTime.toISOString().replace(/\.[0-9]{3}Z$/, '+08:00'),
                id_token: tokens.id_token,
                last_refresh: now.toISOString().replace(/\.[0-9]{3}Z$/, '+08:00'),
                refresh_token: tokens.refresh_token,
                type: 'codex'
            };

            const outputDir = path.join(process.cwd(), 'tokens');
            if (!fs.existsSync(outputDir)) {
                fs.mkdirSync(outputDir, { recursive: true });
            }

            const filename = `token_${Date.now()}.json`;
            const filepath = path.join(outputDir, filename);
            fs.writeFileSync(filepath, JSON.stringify(outData, null, 2));

            console.log(`[OAuth] Token 成功保存至: ${filepath}`);
            return outData;
        } catch (error) {
            console.error('[OAuth] 换取 Token 失败:', error.response ? error.response.data : error.message);
            throw error;
        }
    }
}

module.exports = { OAuthService };
