const { ProtocolRegistrar } = require('./src/protocolRegister');
const { generateRandomName, generateRandomPassword } = require('./src/randomIdentity');

// 使用 mailInboxUrl 中的邮箱直接测试，排除 DDG 邮箱问题
async function debug() {
    // 从 JWT 解码出邮箱
    const jwt = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhZGRyZXNzIjoiYXRveWE1OUBkZXYucGF0aHd5emUuY28iLCJhZGRyZXNzX2lkIjoyfQ.nM0k6jzB9uCVTfP4A1K2RtCu_DrFz7sUG2xc7fY86fg';
    const payload = JSON.parse(Buffer.from(jwt.split('.')[1], 'base64').toString());
    const addr = payload.address;

    const pwd = generateRandomPassword();
    const name = generateRandomName();

    console.log('Email:', addr);
    console.log('Password:', pwd);
    console.log('Name:', name);

    const reg = new ProtocolRegistrar();

    // Step 0
    console.log('\n=== Step 0: Init OAuth ===');
    let r = await reg.step0_initOAuthSession(addr);
    console.log('Step 0 result:', JSON.stringify(r));
    if (!r.ok) {
        console.log('Cookies:', Object.keys(reg.cookies).join(', '));
        process.exit(1);
    }

    // Step 1
    console.log('\n=== Step 1: Register ===');
    r = await reg.step1_registerUser(addr, pwd);
    console.log('Step 1 result:', JSON.stringify(r));
    if (!r.ok) {
        process.exit(1);
    }

    console.log('\nStep 1 passed! Email:', addr);
}
debug().catch(e => { console.error('Error:', e.message); process.exit(1); });
