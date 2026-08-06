const axios = require('axios');
const WebSocket = require('ws');

class BrowserbaseService {
    constructor() {
        this.sessionId = null;
        this.sessionUrl = null;
        this.agentStream = null;
        this.wsConnection = null;
        this.messageId = 1;
        this.pendingCommands = new Map();
    }

    /**
     * 创建新的 Browserbase 会话
     * @returns {Promise<{sessionId: string, sessionUrl: string, wsUrl: string}>}
     */
    async createSession() {
        try {
            const response = await axios.post(
                'https://gemini.browserbase.com/api/session',
                { timezone: 'HKT' },
                {
                    headers: {
                        'Content-Type': 'application/json'
                    }
                }
            );

            const data = response.data;
            if (!data.success) {
                throw new Error('创建会话失败: success=false');
            }

            this.sessionId = data.sessionId;
            this.sessionUrl = data.sessionUrl;

            // 从 sessionUrl 中提取 WSS 地址
            const wsMatch = data.sessionUrl.match(/wss=([^&]+)/);
            const wsUrl = wsMatch ? decodeURIComponent(wsMatch[1]) : null;

            console.log(`[Browserbase] 会话已创建: ${this.sessionId}`);
            console.log(`[Browserbase] Session URL: ${this.sessionUrl}`);

            return {
                sessionId: this.sessionId,
                sessionUrl: this.sessionUrl,
                wsUrl
            };
        } catch (error) {
            console.error('[Browserbase] 创建会话失败:', error.message);
            if (error.response) {
                console.error('[Browserbase] 响应状态:', error.response.status);
                console.error('[Browserbase] 响应数据:', error.response.data);
            }
            throw error;
        }
    }

    /**
     * 发送 Agent 任务流
     * @param {string} goal - 任务目标 Prompt
     * @returns {Promise<void>} - 返回 EventStream（不处理）
     */
    async sendAgentGoal(goal) {
        if (!this.sessionId) {
            throw new Error('会话未创建，请先调用 createSession()');
        }

        try {
            const encodedGoal = encodeURIComponent(goal);
            const model = encodeURIComponent('google/gemini-3-flash-preview');
            const url = `https://gemini.browserbase.com/api/agent/stream?sessionId=${this.sessionId}&goal=${encodedGoal}&model=${model}`;
            
            console.log(`[Browserbase] 发送 Agent 任务 (model: google/gemini-3-flash-preview)...`);
            console.log(`[Browserbase] Goal: ${goal.substring(0, 100)}...`);

            // 发起 GET 请求，接收 EventStream
            const response = await axios.get(url, {
                responseType: 'stream'
            });

            console.log('[Browserbase] Agent 任务已发送，EventStream 开始...');

            const stream = response.data;
            this.agentStream = stream;
            stream.on('error', (streamError) => {
                console.error('[Browserbase] Agent EventStream 错误:', streamError.message);
            });
            stream.on('close', () => {
                if (this.agentStream === stream) {
                    this.agentStream = null;
                }
            });

            // 收到首个 SSE 事件后主动断开，避免持续吃下行带宽。
            let streamClosed = false;
            const closeStream = () => {
                if (streamClosed) {
                    return;
                }

                streamClosed = true;
                stream.destroy();
                if (this.agentStream === stream) {
                    this.agentStream = null;
                }
            };

            stream.once('data', () => {
                setTimeout(closeStream, 250);
            });

            // 某些情况下首个 data 事件会很晚，兜底在短延迟后关闭。
            setTimeout(closeStream, 2000);
            stream.resume();

            return stream;
        } catch (error) {
            console.error('[Browserbase] 发送 Agent 任务失败:', error.message);
            throw error;
        }
    }

    /**
     * 规范化 Browserbase inspector 暴露的 WebSocket URL
     * @param {string} wsUrl
     * @returns {string}
     */
    normalizeWsUrl(wsUrl) {
        if (!wsUrl) {
            return '';
        }

        const decodedUrl = decodeURIComponent(wsUrl);
        if (decodedUrl.startsWith('wss://') || decodedUrl.startsWith('ws://')) {
            return decodedUrl;
        }

        return `wss://${decodedUrl}`;
    }

    /**
     * 发送 CDP 命令并等待响应
     * @param {string} method - CDP 方法名
     * @param {object} params - 参数
     * @returns {Promise<object>} - 响应结果
     */
    sendCDPCommand(method, params = {}) {
        return new Promise((resolve, reject) => {
            if (!this.wsConnection || this.wsConnection.readyState !== WebSocket.OPEN) {
                reject(new Error('WebSocket 未连接'));
                return;
            }

            const id = this.messageId++;
            const message = JSON.stringify({ id, method, params });
            const timeoutId = setTimeout(() => {
                this.pendingCommands.delete(id);
                reject(new Error('CDP 命令超时'));
            }, 5000);

            this.pendingCommands.set(id, { resolve, reject, timeoutId });

            try {
                this.wsConnection.send(message);
            } catch (error) {
                clearTimeout(timeoutId);
                this.pendingCommands.delete(id);
                reject(error);
            }
        });
    }

    /**
     * 清理所有未完成的 CDP 命令
     * @param {string} reason
     */
    clearPendingCommands(reason = 'CDP 连接已关闭') {
        for (const [id, pending] of this.pendingCommands.entries()) {
            clearTimeout(pending.timeoutId);
            pending.reject(new Error(reason));
            this.pendingCommands.delete(id);
        }
    }

    /**
     * 获取当前浏览器上下文中的全部 targets
     * @returns {Promise<Array<object>>}
     */
    async getTargets() {
        const result = await this.sendCDPCommand('Target.getTargets');
        return Array.isArray(result?.targetInfos) ? result.targetInfos : [];
    }

    /**
     * 连接到 CDP WebSocket 并监控 URL 变化（主动轮询）
     * @param {string} wsUrl - WebSocket URL
     * @param {object} options - 监控选项
     * @param {string} options.targetKeyword - 目标关键词（如 'pricing' 或 'localhost'）
     * @param {function} options.targetMatcher - 目标 URL 匹配函数
     * @param {string} options.targetLabel - 目标描述，用于日志
     * @param {function} options.onUrlChange - URL 变化回调
     * @param {function} options.onTargetReached - 达到目标回调
     * @param {number} options.timeout - 超时时间（毫秒）
     * @param {number} options.pollInterval - 轮询间隔（毫秒）
     * @returns {Promise<void>}
     */
    connectToCDP(wsUrl, options = {}) {
        return new Promise((resolve, reject) => {
            const { 
                targetKeyword, 
                targetMatcher,
                targetLabel,
                onUrlChange, 
                onTargetReached, 
                timeout = 1800000,
                pollInterval = 3000 
            } = options;
            const reconnectDelay = 500;
            const staleReconnectMs = 12000;
            const targetDescription = targetLabel || targetKeyword || '目标页面';
            
            const fullWsUrl = this.normalizeWsUrl(wsUrl);
            
            console.log(`[Browserbase] 连接到 CDP: ${fullWsUrl.substring(0, 60)}...`);
            
            let settled = false;
            let pollTimer = null;
            let reconnectTimer = null;
            const targetUrls = new Map();
            let lastUrlChangeAt = Date.now();
            let lastReconnectAt = 0;
            let pollInFlight = false;
            let hasLoggedConnectionReady = false;
            
            const timeoutId = setTimeout(() => {
                cleanup();
                settleReject(new Error('CDP 连接超时'));
            }, timeout);

            const cleanup = () => {
                clearTimeout(timeoutId);
                if (pollTimer) {
                    clearInterval(pollTimer);
                    pollTimer = null;
                }
                if (reconnectTimer) {
                    clearTimeout(reconnectTimer);
                    reconnectTimer = null;
                }
                if (this.wsConnection) {
                    this.clearPendingCommands('CDP 连接已关闭');
                    this.wsConnection.close();
                    this.wsConnection = null;
                }
            };

            const settleResolve = (value) => {
                if (settled) {
                    return;
                }

                settled = true;
                cleanup();
                resolve(value);
            };

            const settleReject = (error) => {
                if (settled) {
                    return;
                }

                settled = true;
                cleanup();
                reject(error);
            };

            const scheduleReconnect = (reason) => {
                if (settled || reconnectTimer) {
                    return;
                }

                lastReconnectAt = Date.now();
                reconnectTimer = setTimeout(() => {
                    reconnectTimer = null;
                    connect();
                }, reconnectDelay);
            };

            const resolveWithUrl = (currentUrl) => {
                if (onTargetReached) {
                    const result = onTargetReached(currentUrl);
                    settleResolve(result || currentUrl);
                    return;
                }

                settleResolve(currentUrl);
            };

            const isTargetUrl = (currentUrl) => {
                if (!currentUrl) {
                    return false;
                }

                if (typeof targetMatcher === 'function') {
                    return targetMatcher(currentUrl);
                }

                if (targetKeyword) {
                    return currentUrl.includes(targetKeyword);
                }

                return false;
            };

            const handleObservedUrl = (currentUrl) => {
                lastUrlChangeAt = Date.now();
                console.log(`[Browserbase] URL 变化: ${currentUrl}`);

                if (onUrlChange) {
                    onUrlChange(currentUrl);
                }

                if (isTargetUrl(currentUrl)) {
                    console.log(`[Browserbase] 检测到${targetDescription}`);
                    resolveWithUrl(currentUrl);
                    return true;
                }

                return false;
            };

            const observeTargetUrl = (targetKey, currentUrl) => {
                if (!currentUrl || currentUrl === 'about:blank') {
                    return false;
                }

                if (targetUrls.get(targetKey) === currentUrl) {
                    return false;
                }

                targetUrls.set(targetKey, currentUrl);
                return handleObservedUrl(currentUrl);
            };

            const pollTargets = async () => {
                if (pollInFlight || settled || !this.wsConnection || this.wsConnection.readyState !== WebSocket.OPEN) {
                    return;
                }

                pollInFlight = true;
                try {
                    let sawNewUrl = false;
                    const targets = await this.getTargets();

                    for (const target of targets) {
                        if (target.type && target.type !== 'page') {
                            continue;
                        }

                        const currentUrl = target.url || '';
                        const targetKey = target.targetId || currentUrl;
                        if (observeTargetUrl(targetKey, currentUrl)) {
                            return;
                        }

                        if (currentUrl && currentUrl !== 'about:blank') {
                            sawNewUrl = true;
                        }
                    }

                    if (!sawNewUrl) {
                        const now = Date.now();
                        if (now - lastUrlChangeAt >= staleReconnectMs && now - lastReconnectAt >= staleReconnectMs) {
                            scheduleReconnect('长时间未观测到新 URL，主动刷新 page target 绑定');
                        }
                    }
                } catch (error) {
                    const now = Date.now();
                    if (now - lastUrlChangeAt >= staleReconnectMs && now - lastReconnectAt >= staleReconnectMs) {
                        scheduleReconnect('CDP 轮询长时间无响应，主动刷新 page target 绑定');
                    }
                } finally {
                    pollInFlight = false;
                }
            };

            const connect = () => {
                if (settled) return;

                this.wsConnection = new WebSocket(fullWsUrl);
                
                this.wsConnection.on('open', () => {
                    this.messageId = 1;
                    lastReconnectAt = Date.now();
                    
                    // 只启用 Target 发现，避免 Page/Runtime/Network 持续推送高频事件。
                    this.wsConnection.send(JSON.stringify({ id: this.messageId++, method: 'Target.setDiscoverTargets', params: { discover: true } }));

                    if (!hasLoggedConnectionReady) {
                        console.log('[Browserbase] CDP WebSocket 已连接');
                        console.log('[Browserbase] 已启用多标签页 URL 监控');
                        hasLoggedConnectionReady = true;
                    }

                    // 开始定期轮询 URL
                    pollTimer = setInterval(pollTargets, pollInterval);
                    
                    // 立即轮询一次，减少目标页出现得过快时的漏判窗口。
                    pollTargets();
                });

                this.wsConnection.on('message', (data) => {
                    try {
                        const message = JSON.parse(data.toString());

                        if (Object.prototype.hasOwnProperty.call(message, 'id') && this.pendingCommands.has(message.id)) {
                            const pending = this.pendingCommands.get(message.id);
                            clearTimeout(pending.timeoutId);
                            this.pendingCommands.delete(message.id);

                            if (message.error) {
                                pending.reject(new Error(message.error.message || 'CDP 命令失败'));
                            } else {
                                pending.resolve(message.result);
                            }
                            return;
                        }

                        if (message.method === 'Target.targetCreated' || message.method === 'Target.targetInfoChanged') {
                            const info = message.params?.targetInfo;
                            if (info?.type === 'page') {
                                if (observeTargetUrl(info.targetId || info.url || 'page', info.url || '')) {
                                    return;
                                }
                                setTimeout(pollTargets, 150);
                            }
                        }
                    } catch (e) {
                        // 忽略解析错误
                    }
                });

                this.wsConnection.on('error', (error) => {
                    console.error('[Browserbase] CDP WebSocket 错误:', error.message);
                    this.clearPendingCommands(`CDP 连接异常: ${error.message}`);
                    scheduleReconnect('CDP 连接异常');
                });

                this.wsConnection.on('unexpected-response', (_request, response) => {
                    const statusCode = response?.statusCode;
                    this.clearPendingCommands(`CDP WebSocket 握手失败: HTTP ${statusCode}`);

                    if (statusCode === 410) {
                        settleReject(new Error('Browserbase 会话已结束，未在结束前观测到目标页面'));
                        return;
                    }

                    scheduleReconnect(`CDP WebSocket 握手失败: HTTP ${statusCode}`);
                });

                this.wsConnection.on('close', () => {
                    this.clearPendingCommands('page websocket 已结束');
                    scheduleReconnect('page websocket 已结束');
                });
            };

            connect();
        });
    }

    /**
     * 关闭 WebSocket 连接
     */
    disconnect() {
        if (this.agentStream) {
            this.agentStream.destroy();
            this.agentStream = null;
        }

        if (this.wsConnection) {
            this.wsConnection.close();
            this.wsConnection = null;
        }
    }
}

module.exports = { BrowserbaseService };
