const crypto = require('crypto');
const axios = require('axios');

const USER_AGENT =
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) ' +
    'AppleWebKit/537.36 (KHTML, like Gecko) ' +
    'Chrome/145.0.0.0 Safari/537.36';

const SENTINEL_API_URL = 'https://sentinel.openai.com/backend-api/sentinel/req';

class SentinelTokenGenerator {
    static MAX_ATTEMPTS = 500000;
    static ERROR_PREFIX = 'wQ8Lk5FbGpA2NcR9dShT6gYjU7VxZ4D';

    constructor(deviceId) {
        this.deviceId = deviceId || crypto.randomUUID();
        this.requirementsSeed = String(Math.random());
        this.sid = crypto.randomUUID();
    }

    /**
     * FNV-1a 32-bit hash (与 OpenAI 前端一致)
     */
    static _fnv1a32(text) {
        let h = 2166136261;
        for (let i = 0; i < text.length; i++) {
            h ^= text.charCodeAt(i);
            h = Math.imul(h, 16777619) >>> 0;
        }
        h ^= h >>> 16;
        h = Math.imul(h, 2246822507) >>> 0;
        h ^= h >>> 13;
        h = Math.imul(h, 3266489909) >>> 0;
        h ^= h >>> 16;
        h = (h >>> 0);
        return h.toString(16).padStart(8, '0');
    }

    _getConfig() {
        const now = new Date();
        const nowStr = now.toUTCString().replace('GMT', 'GMT+0000 (Coordinated Universal Time)');
        const perfNow = Math.random() * 49000 + 1000;
        const timeOrigin = Date.now() - perfNow;

        const navProps = [
            'vendorSub', 'productSub', 'vendor', 'maxTouchPoints', 'doNotTrack',
            'connection', 'plugins', 'mimeTypes', 'cookieEnabled', 'credentials',
            'mediaDevices', 'permissions', 'locks', 'hardwareConcurrency',
        ];
        const docKeys = ['location', 'implementation', 'URL', 'documentURI', 'compatMode'];
        const winKeys = ['Object', 'Function', 'Array', 'Number', 'parseFloat', 'undefined'];

        return [
            '1920x1080',
            nowStr,
            4294705152,
            Math.random(),
            USER_AGENT,
            'https://sentinel.openai.com/sentinel/20260124ceb8/sdk.js',
            null,
            null,
            'en-US',
            'en-US,en',
            Math.random(),
            `${navProps[Math.floor(Math.random() * navProps.length)]}-undefined`,
            docKeys[Math.floor(Math.random() * docKeys.length)],
            winKeys[Math.floor(Math.random() * winKeys.length)],
            perfNow,
            this.sid,
            '',
            [4, 8, 12, 16][Math.floor(Math.random() * 4)],
            timeOrigin,
        ];
    }

    static _base64Encode(data) {
        const json = JSON.stringify(data);
        return Buffer.from(json, 'utf-8').toString('base64');
    }

    _runCheck(startTime, seed, difficulty, config, nonce) {
        config[3] = nonce;
        config[9] = Math.round((Date.now() / 1000 - startTime) * 1000);
        const encoded = SentinelTokenGenerator._base64Encode(config);
        const hashHex = SentinelTokenGenerator._fnv1a32(seed + encoded);
        const prefixLen = difficulty.length;
        if (prefixLen === 0 || hashHex.substring(0, prefixLen) <= difficulty) {
            return encoded + '~S';
        }
        return null;
    }

    generateRequirementsToken() {
        const config = this._getConfig();
        config[3] = 1;
        config[9] = Math.round(Math.random() * 45 + 5);
        return 'gAAAAAC' + SentinelTokenGenerator._base64Encode(config);
    }

    generateToken(seed, difficulty) {
        const useSeed = seed || this.requirementsSeed;
        const useDifficulty = difficulty || '0';
        const config = this._getConfig();
        const start = Date.now() / 1000;

        for (let i = 0; i < SentinelTokenGenerator.MAX_ATTEMPTS; i++) {
            const result = this._runCheck(start, useSeed, useDifficulty, config, i);
            if (result) {
                return 'gAAAAAB' + result;
            }
        }
        return 'gAAAAAB' + SentinelTokenGenerator.ERROR_PREFIX +
            SentinelTokenGenerator._base64Encode(String(null));
    }
}

/**
 * 向 Sentinel API 请求 challenge
 */
async function fetchSentinelChallenge(gen, deviceId, flow = 'authorize_continue') {
    const body = {
        p: gen.generateRequirementsToken(),
        id: deviceId,
        flow: flow,
    };
    const headers = {
        'Content-Type': 'text/plain;charset=UTF-8',
        'Referer': 'https://sentinel.openai.com/backend-api/sentinel/frame.html',
        'User-Agent': USER_AGENT,
        'Origin': 'https://sentinel.openai.com',
        'sec-ch-ua': '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
    };

    try {
        const resp = await axios.post(SENTINEL_API_URL, JSON.stringify(body), {
            headers,
            timeout: 15000,
        });
        if (resp.status !== 200) return null;
        return typeof resp.data === 'object' ? resp.data : null;
    } catch {
        return null;
    }
}

/**
 * 构建完整的 Sentinel Token（包含 challenge 应答）
 * @param {string} deviceId
 * @param {string} flow
 * @param {SentinelTokenGenerator} [existingGen] - 可复用的实例
 */
async function buildSentinelToken(deviceId, flow = 'authorize_continue', existingGen = null) {
    const gen = existingGen || new SentinelTokenGenerator(deviceId);
    const challenge = await fetchSentinelChallenge(gen, deviceId, flow);
    if (!challenge) return null;

    const cValue = challenge.token || '';
    const powData = challenge.proofofwork || {};

    let pValue;
    if (powData && powData.required && powData.seed) {
        pValue = gen.generateToken(String(powData.seed), String(powData.difficulty || '0'));
    } else {
        pValue = gen.generateRequirementsToken();
    }

    return JSON.stringify({
        p: pValue,
        t: '',
        c: cValue,
        id: deviceId,
        flow: flow,
    });
}

module.exports = {
    SentinelTokenGenerator,
    buildSentinelToken,
    fetchSentinelChallenge,
    USER_AGENT,
};
