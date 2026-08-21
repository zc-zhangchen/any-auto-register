const { app, BrowserWindow, dialog } = require('electron')
const { spawn } = require('child_process')
const path = require('path')
const http = require('http')

const PORT = 8000
const isDev = !app.isPackaged

let backendProcess = null
let mainWindow = null

function getBackendPath() {
  if (isDev) {
    return null // 开发模式：手动启动 uvicorn
  }
  // 生产模式：PyInstaller 打包的可执行文件放在 resources/backend/
  const ext = process.platform === 'win32' ? '.exe' : ''
  return path.join(process.resourcesPath, 'backend', 'backend', `backend${ext}`)
}

function startBackend() {
  if (isDev) {
    console.log('[dev] 请先在项目根目录运行 start_backend.bat 或 start_backend.ps1')
    return
  }

  const backendPath = getBackendPath()
  console.log('[backend] 启动:', backendPath)

  backendProcess = spawn(backendPath, [], {
    cwd: path.join(process.resourcesPath, 'backend', 'backend'),
    env: { ...process.env, PORT: String(PORT) },
    stdio: ['ignore', 'pipe', 'pipe'],
  })

  backendProcess.stdout.on('data', (d) => console.log('[backend]', d.toString().trim()))
  backendProcess.stderr.on('data', (d) => console.error('[backend]', d.toString().trim()))

  backendProcess.on('exit', (code) => {
    console.warn('[backend] 进程退出，code:', code)
  })
}

function waitForBackend(retries = 30) {
  return new Promise((resolve, reject) => {
    const attempt = (n) => {
      http.get(`http://localhost:${PORT}/api/platforms`, (res) => {
        if (res.statusCode < 500) resolve()
        else if (n > 0) setTimeout(() => attempt(n - 1), 1000)
        else reject(new Error('后端启动超时'))
      }).on('error', () => {
        if (n > 0) setTimeout(() => attempt(n - 1), 1000)
        else reject(new Error('后端启动超时'))
      })
    }
    attempt(retries)
  })
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    title: 'any-auto-register',
    webPreferences: {
      contextIsolation: true,
    },
  })

  mainWindow.loadURL(`http://localhost:${PORT}`)
  mainWindow.on('closed', () => { mainWindow = null })
}

app.whenReady().then(async () => {
  startBackend()

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
})
