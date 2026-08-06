const path = require('path');
const fs = require('fs');
const { DDGEmailProvider } = require('./src/ddgProvider');
const { ProtocolRegistrar } = require('./src/protocolRegister');
const { OAuthService } = require('./src/oauthService');
const { MailService } = require('./src/mailService');
const { generateRandomName, generateRandomPassword } = require('./src/randomIdentity');
const config = require('./src/config');

// 目标生成数量
const TARGET_COUNT = parseInt(process.argv[2], 10) || 1;

/**
 * 生成随机用户数据
 */
function generateUserData() {
    const fullName = generateRandomName();
    const password = generateRandomPassword();
    
    const age = 25 + Math.floor(Math.random() * 16);
    const birthYear = new Date().getFullYear() - age;
    const birthMonth = 1 + Math.floor(Math.random() * 12);
    const birthDay = 1 + Math.floor(Math.random() * 28);
    const birthDate = `${birthYear}-${String(birthMonth).padStart(2, '0')}-${String(birthDay).padStart(2, '0')}`;
    
    return {
        fullName,
        password,
        age,
        birthDate,
        birthMonth,
        birthDay,
        birthYear
    };
}

/**
 * 第一阶段：纯协议 ChatGPT 注册
 */
async function phase1(emailProvider, mailService, userData) {
    console.log('\n=========================================');
    console.log('[阶段1] 开始 ChatGPT 协议注册流程');
    console.log('=========================================');
    
    const registrar = new ProtocolRegistrar();
    
    const result = await registrar.register(
        emailProvider.getEmail(),
        userData.password,
        userData.fullName,
        userData.birthDate,
        async (otpRequestedAt) => {
            return await mailService.waitForCode({
                timeout: config.otpTimeout,
                pollInterval: config.otpPollInterval,
                notBeforeTs: otpRequestedAt,
            });
        }
    );
    
    if (!result.success) {
        throw new Error(`ChatGPT 注册失败: ${result.reason}`);
    }
    
    console.log('[阶段1] ChatGPT 账户注册成功！');
    return true;
}

/**
 * 第二阶段：纯协议 Codex OAuth 授权
 */
async function phase2(emailProvider, mailService, oauthService, userData) {
    console.log('\n=========================================');
    console.log('[阶段2] 开始 Codex OAuth 协议授权流程');
    console.log('=========================================');
    
    const result = await oauthService.protocolOAuth(
        emailProvider.getEmail(),
        userData.password,
        async (otpRequestedAt) => {
            return await mailService.waitForCode({
                timeout: config.otpTimeout,
                pollInterval: config.otpPollInterval,
                notBeforeTs: otpRequestedAt,
            });
        }
    );
    
    if (!result.success) {
        throw new Error(`OAuth 授权失败: ${result.reason}`);
    }
    
    console.log(`[阶段2] 成功获取授权码: ${result.code.substring(0, 10)}...`);
    
    // 用授权码换取 Token
    const tokenData = await oauthService.exchangeTokenAndSave(result.code, emailProvider.getEmail());
    
    return tokenData;
}

/**
 * 单次注册流程
 */
async function runSingleRegistration() {
    console.log('\n=========================================');
    console.log('[主程序] 开始一次全新的注册与授权流程');
    console.log('=========================================');
    
    const emailProvider = new DDGEmailProvider();
    const mailService = new MailService(config.mailInboxUrl);
    const oauthService = new OAuthService();
    
    try {
        // 0. 生成用户数据
        const userData = generateUserData();
        console.log(`[主程序] 用户数据已生成:`);
        console.log(`  - 姓名: ${userData.fullName}`);
        console.log(`  - 年龄: ${userData.age}`);
        console.log(`  - 出生日期: ${userData.birthDate}`);
        
        // 1. 生成邮箱别名
        await emailProvider.generateAlias();
        
        // 2. 第一阶段：协议注册 ChatGPT
        await phase1(emailProvider, mailService, userData);
        
        // 3. 第二阶段：协议 OAuth 授权
        const tokenData = await phase2(emailProvider, mailService, oauthService, userData);
        
        console.log('[主程序] 本次注册流程圆满结束！');
        console.log(`[主程序] Token 已保存，邮箱: ${tokenData.email}`);
        
        return true;
        
    } catch (error) {
        console.error('[主程序] 本次任务执行失败:', error.message);
        throw error;
    }
}

/**
 * 检查 token 数量
 */
async function checkTokenCount() {
    const outputDir = path.join(process.cwd(), 'tokens');
    if (!fs.existsSync(outputDir)) {
        return 0;
    }
    const files = fs.readdirSync(outputDir).filter(f => f.startsWith('token_') && f.endsWith('.json'));
    return files.length;
}

/**
 * 归档已有 tokens
 */
function archiveExistingTokens() {
    const outputDir = path.join(process.cwd(), 'tokens');
    if (!fs.existsSync(outputDir)) return;
    
    const files = fs.readdirSync(outputDir).filter(f => f.startsWith('token_') && f.endsWith('.json'));
    for (const file of files) {
        const oldPath = path.join(outputDir, file);
        const newPath = path.join(outputDir, `old_${file}`);
        fs.renameSync(oldPath, newPath);
        console.log(`[归档] ${file} → old_${file}`);
    }
}

/**
 * 启动批量注册
 */
async function startBatch() {
    console.log(`[启动] 开始执行 Codex 协议注册机，目标生成数量: ${TARGET_COUNT}`);
    
    // 检查配置
    if (!config.ddgToken) {
        console.error('[错误] 未配置 ddgToken，请检查 config.json 文件');
        process.exit(1);
    }
    if (!config.mailInboxUrl) {
        console.error('[错误] 未配置 mailInboxUrl，请检查 config.json 文件');
        process.exit(1);
    }
    
    // 归档已有的 token 文件
    archiveExistingTokens();
    
    while (true) {
        const currentCount = await checkTokenCount();
        if (currentCount >= TARGET_COUNT) {
            console.log(`\n[完成] 当前 Token 文件数量 (${currentCount}) 已达到目标 (${TARGET_COUNT})。程序退出。`);
            break;
        }
        
        console.log(`\n[进度] 目前 Token 数量 ${currentCount} / 目标 ${TARGET_COUNT}`);
        
        try {
            await runSingleRegistration();
        } catch (error) {
            console.error('[主程序] 注册失败，10 秒后重试...');
            await new Promise(resolve => setTimeout(resolve, 10000));
        }
    }
}

startBatch().catch(console.error);
