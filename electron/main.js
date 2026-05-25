const { app, BrowserWindow, dialog } = require('electron')
const { spawn } = require('child_process')
const path = require('path')
const http = require('http')
const fs = require('fs')

const PORT = 8000
const BACKEND_WAIT_RETRIES = 180
const isDev = !app.isPackaged

let backendProcess = null
let mainWindow = null
let backendLogStream = null

function writeBackendLog(message) {
  const line = `[${new Date().toISOString()}] ${message}\n`
  console.log(message)
  if (backendLogStream) backendLogStream.write(line)
}

function getBackendPath() {
  if (isDev) {
    return null // 开发模式：手动启动 uvicorn
  }
  // 生产模式：PyInstaller 打包的可执行文件放在 resources/backend/
  const ext = process.platform === 'win32' ? '.exe' : ''
  return path.join(process.resourcesPath, 'backend', `backend${ext}`)
}

function getBackendLogPath() {
  const logDir = process.platform === 'darwin'
    ? path.join(app.getPath('home'), 'Library', 'Logs', 'Any Auto Register')
    : app.getPath('userData')
  fs.mkdirSync(logDir, { recursive: true })
  return path.join(logDir, 'backend.log')
}

function startBackend() {
  if (isDev) {
    console.log('[dev] 请先在项目根目录运行 start_backend.bat 或 start_backend.ps1')
    return
  }

  const backendPath = getBackendPath()
  const logPath = getBackendLogPath()
  backendLogStream = fs.createWriteStream(logPath, { flags: 'a' })
  writeBackendLog(`[backend] 日志文件: ${logPath}`)
  writeBackendLog(`[backend] 启动: ${backendPath}`)

  if (!fs.existsSync(backendPath)) {
    throw new Error(`后端可执行文件不存在: ${backendPath}`)
  }

  backendProcess = spawn(backendPath, [], {
    cwd: path.join(process.resourcesPath, 'backend'),
    env: { ...process.env, PORT: String(PORT) },
    stdio: ['ignore', 'pipe', 'pipe'],
  })

  backendProcess.stdout.on('data', (d) => writeBackendLog(`[backend:stdout] ${d.toString().trim()}`))
  backendProcess.stderr.on('data', (d) => writeBackendLog(`[backend:stderr] ${d.toString().trim()}`))

  backendProcess.on('exit', (code) => {
    writeBackendLog(`[backend] 进程退出，code: ${code}`)
  })

  backendProcess.on('error', (err) => {
    writeBackendLog(`[backend] 启动失败: ${err.stack || err.message || err}`)
  })
}

function waitForBackend(retries = BACKEND_WAIT_RETRIES) {
  return new Promise((resolve, reject) => {
    const logPath = getBackendLogPath()
    const attempt = (n) => {
      http.get(`http://localhost:${PORT}/api/platforms`, (res) => {
        if (res.statusCode < 500) resolve()
        else if (n > 0) setTimeout(() => attempt(n - 1), 1000)
        else reject(new Error(`后端启动超时，请查看日志: ${logPath}`))
      }).on('error', () => {
        if (n > 0) setTimeout(() => attempt(n - 1), 1000)
        else reject(new Error(`后端启动超时，请查看日志: ${logPath}`))
      })
    }
    attempt(retries)
  })
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    title: 'Account Manager',
    webPreferences: {
      contextIsolation: true,
    },
  })

  mainWindow.loadURL(`http://localhost:${PORT}`)
  mainWindow.on('closed', () => { mainWindow = null })
}

app.whenReady().then(async () => {
  try {
    startBackend()
  } catch (err) {
    dialog.showErrorBox('启动失败', err.message)
    app.quit()
    return
  }

  try {
    await waitForBackend()
  } catch (err) {
    dialog.showErrorBox('启动失败', err.message)
    app.quit()
    return
  }

  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

app.on('will-quit', () => {
  if (backendProcess) {
    backendProcess.kill()
    backendProcess = null
  }
  if (backendLogStream) {
    backendLogStream.end()
    backendLogStream = null
  }
})
