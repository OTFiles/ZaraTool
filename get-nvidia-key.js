#!/usr/bin/env node

/**
 * NVIDIA API Key 生成脚本 (Node.js)
 * 
 * 模拟油猴脚本的两步流程：
 * 1. GET /user-context 获取 orgName
 * 2. POST /v3/orgs/${orgName}/keys/type/AI_PLAYGROUNDS_KEY 创建 AI Playground Key
 * 
 * 用法:
 *   NVIDIA_COOKIE="cookie_string" node get-nvidia-key.js
 *   node get-nvidia-key.js "cookie_string"
 * 
 * 输出: 若成功则打印 API Key，否则打印错误信息并退出(1)
 */

if (!globalThis.fetch) {
  console.error('错误: 当前 Node.js 版本不支持 fetch (需要 18+ 或启用 --experimental-fetch)');
  process.exit(1);
}

const cookie = process.env.NVIDIA_COOKIE || process.argv[2];
if (!cookie) {
  console.error('用法: NVIDIA_COOKIE="cookie_string" node get-nvidia-key.js');
  console.error('  或: node get-nvidia-key.js "cookie_string"');
  process.exit(1);
}

const BASE_HEADERS = {
  'accept': 'application/json, text/plain, */*',
  'cookie': cookie,
  'referer': 'https://build.nvidia.com/',
  'origin': 'https://build.nvidia.com',
  'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36'
};

async function safeReadResponse(res) {
  const contentType = res.headers.get('content-type') || '';
  return contentType.includes('application/json') ? res.json() : res.text();
}

async function getOrCreateApiKey() {
  // ----- 第一步：获取用户上下文，提取 orgName -----
  console.error('📡 步骤 1/2: 获取用户信息...');
  const step1Res = await fetch('https://api.ngc.nvidia.com/user-context', {
    method: 'GET',
    headers: BASE_HEADERS
  });

  const step1Data = await safeReadResponse(step1Res);
  if (!step1Res.ok) {
    throw new Error(`步骤1失败 (${step1Res.status}): ${JSON.stringify(step1Data, null, 2)}`);
  }

  const orgName = step1Data?.orgName;
  if (!orgName) {
    throw new Error(`步骤1响应缺少 orgName 字段: ${JSON.stringify(step1Data, null, 2)}`);
  }
  console.error(`✅ 用户: ${step1Data.name || '未知'}, 组织: ${orgName}`);

  // ----- 第二步：创建 AI_PLAYGROUNDS_KEY -----
  console.error('📡 步骤 2/2: 创建 API Key...');
  const payload = {
    expiryDate: '2126-04-08T07:00:00Z',
    name: 'dev',
    type: 'AI_PLAYGROUNDS_KEY',
    policies: [
      {
        product: 'nv-cloud-functions',
        scopes: ['invoke_function'],
        resources: [{ id: '*', type: 'account-functions' }]
      }
    ]
  };

  const step2Res = await fetch(
    `https://api.ngc.nvidia.com/v3/orgs/${orgName}/keys/type/AI_PLAYGROUNDS_KEY`,
    {
      method: 'POST',
      headers: {
        ...BASE_HEADERS,
        'content-type': 'application/json',
        'accept': '*/*'
      },
      body: JSON.stringify(payload)
    }
  );

  const step2Data = await safeReadResponse(step2Res);

  if (!step2Res.ok) {
    if (step2Res.status === 409) {
      throw new Error('Key 已存在 (409 Conflict)。可尝试删除旧 Key 后重新生成，或改用不同 name。');
    }
    throw new Error(`步骤2失败 (${step2Res.status}): ${JSON.stringify(step2Data, null, 2)}`);
  }

  // ===== 修复点：直接从 apiKey 字段提取 =====
  const apiKey = step2Data?.apiKey?.value;
  if (!apiKey) {
    throw new Error(`步骤2响应缺少 apiKey.value: ${JSON.stringify(step2Data, null, 2)}`);
  }

  return apiKey;
}

getOrCreateApiKey()
  .then(key => {
    console.log(key);
  })
  .catch(err => {
    console.error('❌ 失败:', err.message);
    process.exit(1);
  });