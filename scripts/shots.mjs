/**
 * 演示截图生成脚本（真实页面真实数据，非手绘示意图）。
 *
 * 依赖（仅生成截图时需要，不属于应用运行依赖）:
 *   npm i -D puppeteer-core
 *   并准备一个本机 Chrome/Edge，路径通过 CHROME_PATH 指定。
 *
 * 用法:
 *   # 1) 先启动后端（它同时托管前端 dist）:
 *   cd backend && venv/Scripts/python.exe -m uvicorn app.main:app --port 8000
 *   # 2) 抓图:
 *   CHROME_PATH="/c/Program Files/Google/Chrome/Application/chrome.exe" \
 *   NODE_PATH=<含 puppeteer-core 的 node_modules> \
 *   node scripts/shots.mjs http://127.0.0.1:8000
 *
 * 产物: docs/screenshots/*.png
 */
import { mkdir } from 'node:fs/promises'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import puppeteer from 'puppeteer-core'

const BASE = process.argv[2] || 'http://127.0.0.1:8000'
const HERE = dirname(fileURLToPath(import.meta.url))
// ESM 的模块解析只认"脚本所在位置向上查找 node_modules", 不认 NODE_PATH;
// 若 puppeteer-core 装在别处, 可用 OUT_DIR 指定产物目录并把脚本临时拷到该 node_modules 旁执行。
const OUT = process.env.OUT_DIR
  ? resolve(process.env.OUT_DIR)
  : resolve(HERE, '..', 'docs', 'screenshots')
const CHROME =
  process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe'

const VIEWPORT = { width: 1500, height: 940, deviceScaleFactor: 1.5 }

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function main() {
  await mkdir(OUT, { recursive: true })
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-gpu', '--hide-scrollbars', '--font-render-hinting=none'],
    defaultViewport: VIEWPORT,
  })
  const page = await browser.newPage()
  await page.setViewport(VIEWPORT)

  const shot = async (name, { fullPage = true } = {}) => {
    await sleep(600)
    const path = join(OUT, name)
    await page.screenshot({ path, fullPage })
    console.log(`  ✓ ${name}`)
  }

  const goto = async (path) => {
    await page.goto(`${BASE}${path}`, { waitUntil: 'networkidle2', timeout: 60000 })
    // 等 Vue 挂载完成
    await page.waitForFunction(() => document.querySelectorAll('.nav-item').length >= 6, {
      timeout: 20000,
    })
    await sleep(900) // 等首次 API 回填
  }

  console.log('[SHOTS] 抓取页面 ...')

  // 1. 总览看板
  await goto('/')
  await shot('01_dashboard.png', { fullPage: false })

  // 2. 上传入库：真上传一个 DOCX，抓解析结果（路由 / 表格数 / chunk 数）
  await goto('/upload')
  const sample =
    process.env.SAMPLE_FILE || resolve(HERE, '..', 'eval', 'corpus', 'contract.docx')
  const fileInput = await page.$('input[type=file]')
  if (fileInput) {
    await fileInput.uploadFile(sample)
    await sleep(400) // 等 Vue 的 change 处理把 file 写进响应式状态
    await page.evaluate(() => {
      const b = [...document.querySelectorAll('button')].find((x) =>
        x.textContent?.includes('上传并解析'),
      )
      if (b) b.click()
    })
    await page.waitForFunction(() => document.body.innerText.includes('解析结果'), {
      timeout: 60000,
    })
  }
  await shot('02_upload.png', { fullPage: false })

  // 3. 文档管理
  await goto('/documents')
  await shot('03_documents.png', { fullPage: false })

  // 4. Chunk 管理（含受保护表格块）
  await goto('/chunks')
  await shot('04_chunks.png', { fullPage: false })

  // 5. 检索调试：点一次"混合检索"，抓有结果的三层分数
  await goto('/retrieval')
  await page.evaluate(() => {
    const btns = [...document.querySelectorAll('button')]
    const b = btns.find((x) => x.textContent?.includes('混合检索'))
    if (b) b.click()
  })
  await page.waitForFunction(
    () => document.querySelectorAll('.source-card').length > 0,
    { timeout: 30000 },
  )
  await shot('05_retrieval.png')
  const hits = await page.evaluate(() => document.querySelectorAll('.source-card').length)

  // 6. Agent 对话：真发一问，等溯源出来
  await goto('/agent')
  await page.evaluate(() => {
    const input = document.querySelector('input.input')
    if (input) {
      const setter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype,
        'value',
      ).set
      setter.call(input, '入职流程有哪些步骤')
      input.dispatchEvent(new Event('input', { bubbles: true }))
    }
  })
  await page.evaluate(() => {
    const btns = [...document.querySelectorAll('button')]
    const b = btns.find((x) => x.textContent?.trim() === '发送')
    if (b) b.click()
  })
  await page.waitForFunction(
    () => {
      const btns = [...document.querySelectorAll('button')]
      const sending = btns.some((x) => x.textContent?.includes('生成中'))
      const src = document.querySelectorAll('.source-card').length
      return !sending && src > 0
    },
    { timeout: 60000 },
  )
  await shot('06_agent.png', { fullPage: false })
  const srcs = await page.evaluate(() => document.querySelectorAll('.source-card').length)

  // 7. 证据裁判：问一个知识库完全无关的问题，应如实拒答（不编造、无溯源卡片）
  await page.evaluate(() => {
    const input = document.querySelector('input.input')
    if (input) {
      const setter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype,
        'value',
      ).set
      setter.call(input, '请介绍一下量子纠缠在星际航行中的应用')
      input.dispatchEvent(new Event('input', { bubbles: true }))
    }
  })
  await page.evaluate(() => {
    const btns = [...document.querySelectorAll('button')]
    const b = btns.find((x) => x.textContent?.trim() === '发送')
    if (b) b.click()
  })
  await page.waitForFunction(
    () => {
      const btns = [...document.querySelectorAll('button')]
      const sending = btns.some((x) => x.textContent?.includes('生成中'))
      const body = document.body.innerText || ''
      return !sending && body.includes('知识库中没有找到')
    },
    { timeout: 60000 },
  )
  await sleep(400)
  await shot('07_refusal.png', { fullPage: false })

  await browser.close()
  console.log(`[SHOTS] 完成 -> ${OUT}  (检索命中 ${hits} 条, 溯源 ${srcs} 条)`)
}

main().catch((e) => {
  console.error('[SHOTS] 失败:', e)
  process.exit(1)
})
