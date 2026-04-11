const path = require('path');
const fs = require('fs');

const configPath = path.join(__dirname, '..', 'config.json');

// 读取配置文件
function loadConfig() {
    if (!fs.existsSync(configPath)) {
        console.error(`[Config] 配置文件不存在: ${configPath}`);
        console.error('[Config] 请复制 config.example.json 为 config.json 并填入必要参数');
        return {};
    }
    
    try {
        const content = fs.readFileSync(configPath, 'utf8');
        return JSON.parse(content);
    } catch (error) {
        console.error('[Config] 解析配置文件失败:', error.message);
        return {};
    }
}

const config = loadConfig();

module.exports = {
    // DDG Email Alias
    ddgToken: config.ddgToken,
    
    // Mail Inbox
    mailInboxUrl: config.mailInboxUrl,
    
    // OAuth
    oauthClientId: config.oauthClientId || 'app_EMoamEEZ73f0CkXaXp7hrann',
    oauthRedirectPort: parseInt(config.oauthRedirectPort, 10) || 1455,

    // 验证码轮询配置
    otpTimeout: parseInt(config.otpTimeout, 10) || 120,
    otpPollInterval: parseInt(config.otpPollInterval, 10) || 3,
};
