const axios = require('axios');
const crypto = require('crypto');
const { buildSentinelToken, SentinelTokenGenerator, USER_AGENT } = require('./sentinelService');

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

/**
 * 生成随机 Datadog trace headers
 */
function randomTraceHeaders() {
    const traceId = String(crypto.randomInt(0, 2 ** 48 - 1));
    const parentId = String(crypto.randomInt(0, 2 ** 48 - 1));
    const traceHex = BigInt(traceId).toString(16).padStart(16, '0');
    const parentHex = BigInt(parentId).toString(16).padStart(16, '0');
    return {
        'traceparent': `00-0000000000000000${traceHex}-${parentHex}-01`,
        'tracestate': 'dd=s:1;o:rum',
        'x-datadog-origin': 'rum',
        'x-datadog-parent-id': parentId,
        'x-datadog-sampling-priority': '1',
        'x-datadog-trace-id': traceId,
    };
}

/**
 * 纯协议注册器 - 不需要浏览器
 */
class ProtocolRegistrar {
    constructor() {
        this.deviceId = crypto.randomUUID();
        this.cookies = {};
        this.sentinelGen = new SentinelTokenGenerator(this.deviceId);
    }

    /**
     * 收集响应中的 Set-Cookie
     */
    _collectCookies(response) {
        const setCookies = response.headers['set-cookie'];
        if (setCookies) {
            for (const cookieStr of setCookies) {
                const [nameValue] = cookieStr.split(';');
                const eqIdx = nameValue.indexOf('=');
                if (eqIdx > 0) {
                    const name = nameValue.substring(0, eqIdx).trim();
                    const value = nameValue.substring(eqIdx + 1).trim();
                    this.cookies[name] = value;
                }
            }
        }
    }

    /**
     * 构建 Cookie header
     */
    _cookieHeader() {
        return Object.entries(this.cookies)
            .map(([k, v]) => `${k}=${v}`)
            .join('; ');
    }

    /**
     * 发起 HTTP 请求，手动跟随重定向并收集 cookie
     * @param {string} method - GET/POST
     * @param {string} url - 请求 URL
     * @param {object} options - { headers, data, maxRedirects }
     */
    async _request(method, url, options = {}) {
        const { headers = {}, data = null, maxRedirects = 10 } = options;
        let currentUrl = url;
        let redirectCount = 0;

        while (true) {
            const reqHeaders = { ...headers, Cookie: this._cookieHeader() };
            
            try {
                const config = {
                    method: redirectCount === 0 ? method : 'GET',
                    url: currentUrl,
                    headers: reqHeaders,
                    maxRedirects: 0,
                    validateStatus: () => true,
                    timeout: 30000,
                };

                // 只有第一次请求才带 body
                if (redirectCount === 0 && data !== null && data !== undefined) {
                    config.data = data;
                }

                const resp = await axios(config);
                this._collectCookies(resp);

                // 跟随重定向
                if (resp.status >= 300 && resp.status < 400 && resp.headers['location']) {
                    redirectCount++;
                    if (redirectCount > maxRedirects) {
                        return resp;
                    }
                    const location = resp.headers['location'];
                    // 处理相对路径
                    try {
                        currentUrl = new URL(location, currentUrl).toString();
                    } catch {
                        currentUrl = location;
                    }
                    // 如果重定向目标的 host 是 localhost，直接返回（不实际请求）
                    try {
                        const parsedRedirect = new URL(currentUrl);
                        if (parsedRedirect.hostname === 'localhost') {
                            return { ...resp, _redirectedToLocalhost: true, _finalUrl: currentUrl };
                        }
                    } catch {}
                    continue;
                }

                return resp;
            } catch (error) {
                throw error;
            }
        }
    }

    /**
     * 构建带 Sentinel Token 的请求头
     */
    async _buildHeaders(referer, { includeSentinel = false, flow = 'authorize_continue' } = {}) {
        const headers = {
            ...COMMON_HEADERS,
            referer,
            'oai-device-id': this.deviceId,
            ...randomTraceHeaders(),
        };

        if (includeSentinel) {
            const sentinel = await buildSentinelToken(this.deviceId, flow, this.sentinelGen);
            if (!sentinel) {
                console.error('[协议注册] Sentinel Token 生成失败');
                return null;
            }
            headers['openai-sentinel-token'] = sentinel;
        }

        return headers;
    }

    /**
     * 检查是否已获取 login_session cookie
     */
    _hasLoginSession() {
        return 'login_session' in this.cookies;
    }

    /**
     * Step 0: 初始化 OAuth 会话
     */
    async step0_initOAuthSession(email) {
        console.log('[协议注册] Step 0: 初始化 OAuth 会话');

        // 设置 oai-did cookie
        this.cookies['oai-did'] = this.deviceId;

        // 生成 PKCE
        const codeVerifier = crypto.randomBytes(64).toString('base64url');
        const codeChallenge = crypto.createHash('sha256').update(codeVerifier).digest('base64url');
        const state = crypto.randomBytes(16).toString('hex');

        this._codeVerifier = codeVerifier;
        this._state = state;

        const params = new URLSearchParams({
            response_type: 'code',
            client_id: 'app_EMoamEEZ73f0CkXaXp7hrann',
            redirect_uri: 'http://localhost:1455/auth/callback',
            scope: 'openid profile email offline_access',
            code_challenge: codeChallenge,
            code_challenge_method: 'S256',
            state,
            screen_hint: 'signup',
            prompt: 'login',
        });

        const authorizeUrl = `${OPENAI_AUTH_BASE}/oauth/authorize?${params.toString()}`;

        try {
            await this._request('GET', authorizeUrl, { headers: NAVIGATE_HEADERS });
        } catch (error) {
            return { ok: false, reason: `oauth_authorize_failed:${error.message}` };
        }

        if (!this._hasLoginSession()) {
            return { ok: false, reason: 'login_session_missing' };
        }

        // authorize/continue
        const headers = await this._buildHeaders(
            `${OPENAI_AUTH_BASE}/create-account`,
            { includeSentinel: true, flow: 'authorize_continue' }
        );
        if (!headers) {
            return { ok: false, reason: 'sentinel_authorize_continue_failed' };
        }

        try {
            const resp = await this._request('POST',
                `${OPENAI_AUTH_BASE}/api/accounts/authorize/continue`,
                { data: { username: { kind: 'email', value: email }, screen_hint: 'signup' }, headers }
            );

            if (resp.status !== 200) {
                console.error('[协议注册] Step 0 authorize/continue 失败:', resp.status, JSON.stringify(resp.data).substring(0, 500));
                return { ok: false, reason: `authorize_continue_http_${resp.status}` };
            }
        } catch (error) {
            return { ok: false, reason: `authorize_continue_failed:${error.message}` };
        }

        return { ok: true };
    }

    /**
     * Step 1: 提交邮箱和密码
     */
    async step1_registerUser(email, password) {
        console.log('[协议注册] Step 1: 提交邮箱密码');

        const headers = await this._buildHeaders(
            `${OPENAI_AUTH_BASE}/create-account/password`,
            { includeSentinel: true, flow: 'authorize_continue' }
        );
        if (!headers) {
            return { ok: false, reason: 'sentinel_register_user_failed' };
        }

        try {
            const resp = await this._request('POST',
                `${OPENAI_AUTH_BASE}/api/accounts/user/register`,
                { data: { username: email, password }, headers }
            );

            if ([200, 301, 302].includes(resp.status)) {
                return { ok: true };
            }
            console.error('[协议注册] Step 1 注册失败:', resp.status, JSON.stringify(resp.data).substring(0, 500));
            return { ok: false, reason: `user_register_http_${resp.status}` };
        } catch (error) {
            return { ok: false, reason: `user_register_failed:${error.message}` };
        }
    }

    /**
     * Step 2: 触发发送邮箱验证码
     */
    async step2_sendOTP() {
        console.log('[协议注册] Step 2: 触发邮箱 OTP');

        const sendHeaders = {
            ...NAVIGATE_HEADERS,
            referer: `${OPENAI_AUTH_BASE}/create-account/password`,
        };

        try {
            const resp = await this._request('GET',
                `${OPENAI_AUTH_BASE}/api/accounts/email-otp/send`,
                { headers: sendHeaders }
            );
            if (![200, 204, 301, 302].includes(resp.status)) {
                return { ok: false, reason: `email_otp_send_http_${resp.status}` };
            }
        } catch (error) {
            return { ok: false, reason: `email_otp_send_failed:${error.message}` };
        }

        // 访问验证页面
        try {
            await this._request('GET', `${OPENAI_AUTH_BASE}/email-verification`, {
                headers: {
                    ...NAVIGATE_HEADERS,
                    referer: `${OPENAI_AUTH_BASE}/create-account/password`,
                },
            });
        } catch (error) {
            return { ok: false, reason: `email_verification_page_failed:${error.message}` };
        }

        return { ok: true };
    }

    /**
     * Step 3: 校验邮箱验证码
     */
    async step3_validateOTP(code) {
        console.log(`[协议注册] Step 3: 校验邮箱 OTP: ${code}`);

        const headers = await this._buildHeaders(
            `${OPENAI_AUTH_BASE}/email-verification`,
            { includeSentinel: false }
        );
        if (!headers) {
            return { ok: false, reason: 'otp_headers_failed' };
        }

        try {
            const resp = await this._request('POST',
                `${OPENAI_AUTH_BASE}/api/accounts/email-otp/validate`,
                { data: { code }, headers }
            );

            if (resp.status === 200) {
                return { ok: true, data: resp.data };
            }
            return { ok: false, reason: `email_otp_validate_http_${resp.status}` };
        } catch (error) {
            return { ok: false, reason: `email_otp_validate_failed:${error.message}` };
        }
    }

    /**
     * Step 4: 创建账户（提交姓名和生日）
     */
    async step4_createAccount(name, birthdate) {
        console.log(`[协议注册] Step 4: 创建账户 - ${name}, ${birthdate}`);

        const headers = await this._buildHeaders(
            `${OPENAI_AUTH_BASE}/about-you`,
            { includeSentinel: true, flow: 'authorize_continue' }
        );
        if (!headers) {
            return { ok: false, reason: 'create_account_headers_failed' };
        }

        try {
            const resp = await this._request('POST',
                `${OPENAI_AUTH_BASE}/api/accounts/create_account`,
                { data: { name, birthdate }, headers }
            );

            if (resp.status === 200 || resp.status === 301 || resp.status === 302) {
                return { ok: true, data: resp.data };
            }
            if (resp.status === 400 && resp.data && String(resp.data).toLowerCase().includes('already_exists')) {
                return { ok: true, data: resp.data };
            }
            return { ok: false, reason: `create_account_http_${resp.status}` };
        } catch (error) {
            return { ok: false, reason: `create_account_failed:${error.message}` };
        }
    }

    /**
     * 从响应/cookie 中提取 OAuth callback params
     */
    _extractCallbackParams(responseData, responseHeaders, responseUrl) {
        // 从 response payload 中提取
        if (responseData && typeof responseData === 'object') {
            for (const key of ['continue_url', 'callback_url', 'url', 'redirect_url']) {
                const url = responseData[key];
                if (url && typeof url === 'string' && url.includes('code=')) {
                    try {
                        const parsed = new URL(url);
                        const code = parsed.searchParams.get('code');
                        if (code) return { code, state: parsed.searchParams.get('state') };
                    } catch {}
                }
            }
        }

        // 从 response headers Location 中提取
        if (responseHeaders) {
            const location = responseHeaders['location'] || responseHeaders['Location'];
            if (location && location.includes('code=')) {
                try {
                    const parsed = new URL(location);
                    const code = parsed.searchParams.get('code');
                    if (code) return { code, state: parsed.searchParams.get('state') };
                } catch {}
            }
        }

        // 从 cookies 中提取
        for (const [name, value] of Object.entries(this.cookies)) {
            if (typeof value === 'string' && value.includes('code=')) {
                const match = value.match(/code=([^&"'\s]+)/);
                if (match) return { code: match[1] };
            }
        }

        return null;
    }

    /**
     * Step 5: 执行 consent 获取 OAuth code (注册完成后)
     */
    async step5_getOAuthCode() {
        console.log('[协议注册] Step 5: 获取 OAuth Code');

        // 尝试访问 consent 页面获取 code（手动跟随重定向）
        const consentUrl = `${OPENAI_AUTH_BASE}/sign-in-with-chatgpt/codex/consent`;
        try {
            const resp = await this._request('GET', consentUrl, {
                headers: NAVIGATE_HEADERS,
            });

            // 检查是否重定向到了 localhost（包含 code）
            if (resp._redirectedToLocalhost && resp._finalUrl) {
                try {
                    const parsed = new URL(resp._finalUrl);
                    const code = parsed.searchParams.get('code');
                    if (code) {
                        console.log('[协议注册] 从 consent 重定向获取到 code');
                        return { ok: true, code };
                    }
                } catch {}
            }

            const params = this._extractCallbackParams(
                resp.data,
                resp.headers,
                ''
            );
            if (params && params.code) {
                console.log(`[协议注册] 从 consent 页面获取到 code`);
                return { ok: true, code: params.code };
            }
        } catch (error) {
            console.error('[协议注册] consent 请求失败:', error.message);
        }

        return { ok: false, reason: 'oauth_code_not_found' };
    }

    /**
     * 完整注册流程
     * @param {string} email - 邮箱地址
     * @param {string} password - 密码
     * @param {string} name - 全名
     * @param {string} birthdate - 生日 (YYYY-MM-DD)
     * @param {function} waitForCode - 等待验证码的回调函数
     * @returns {Promise<{success: boolean, reason?: string, code?: string}>}
     */
    async register(email, password, name, birthdate, waitForCode) {
        // Step 0: 初始化 OAuth 会话
        let result = await this.step0_initOAuthSession(email);
        if (!result.ok) {
            return { success: false, reason: result.reason };
        }

        // Step 1: 提交邮箱密码
        result = await this.step1_registerUser(email, password);
        if (!result.ok) {
            return { success: false, reason: result.reason };
        }

        // Step 2: 发送 OTP
        const otpRequestedAt = Date.now() / 1000;
        result = await this.step2_sendOTP();
        if (!result.ok) {
            return { success: false, reason: result.reason };
        }

        // 等待验证码
        console.log('[协议注册] 等待邮箱验证码...');
        const code = await waitForCode(otpRequestedAt);
        if (!code) {
            return { success: false, reason: 'verify_code_timeout' };
        }

        // Step 3: 校验 OTP
        result = await this.step3_validateOTP(code);
        if (!result.ok) {
            return { success: false, reason: result.reason };
        }

        // Step 4: 创建账户
        result = await this.step4_createAccount(name, birthdate);
        if (!result.ok) {
            return { success: false, reason: result.reason };
        }

        console.log('[协议注册] ChatGPT 账户注册成功！');
        return { success: true };
    }

    /**
     * code_verifier getter (for external OAuth token exchange)
     */
    get codeVerifier() {
        return this._codeVerifier;
    }

    get state() {
        return this._state;
    }
}

module.exports = { ProtocolRegistrar, OPENAI_AUTH_BASE };
