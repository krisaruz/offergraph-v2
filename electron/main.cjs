const { app, BrowserWindow, shell } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const http = require('http');

const isDev = !app.isPackaged;
const BACKEND_PORT = 8000;
const FRONTEND_PORT = isDev ? 3000 : 35231;

let mainWindow = null;
let backendProcess = null;
let frontendProcess = null;

function waitForServer(port, timeout = 30000) {
  const start = Date.now();
  return new Promise((resolve, reject) => {
    const check = () => {
      const req = http.get(`http://127.0.0.1:${port}/`, (res) => {
        resolve();
      });
      req.on('error', () => {
        if (Date.now() - start > timeout) {
          reject(new Error(`Server on port ${port} not ready after ${timeout}ms`));
        } else {
          setTimeout(check, 500);
        }
      });
      req.end();
    };
    check();
  });
}

function startBackend() {
  if (isDev) return null;

  const pythonPath = path.join(process.resourcesPath, 'python', 'python.exe');
  const backendDir = path.join(app.getAppPath(), 'backend');

  backendProcess = spawn(pythonPath, [
    '-m', 'uvicorn', 'app.main:app',
    '--host', '127.0.0.1',
    '--port', String(BACKEND_PORT),
  ], {
    cwd: backendDir,
    env: { ...process.env, PYTHONPATH: backendDir },
    stdio: 'pipe',
  });

  backendProcess.stdout.on('data', (data) => {
    console.log(`[backend] ${data}`);
  });

  backendProcess.stderr.on('data', (data) => {
    console.error(`[backend] ${data}`);
  });

  return backendProcess;
}

function startFrontend() {
  if (isDev) return null;

  const nodePath = process.execPath;
  const frontendDir = path.join(app.getAppPath(), 'frontend');
  const nextBin = path.join(frontendDir, 'node_modules', '.bin', 'next');

  frontendProcess = spawn(nodePath, [
    nextBin, 'start', '-p', String(FRONTEND_PORT), '-H', '127.0.0.1',
  ], {
    cwd: frontendDir,
    env: {
      ...process.env,
      NEXT_PUBLIC_API_URL: `http://127.0.0.1:${BACKEND_PORT}`,
    },
    stdio: 'pipe',
  });

  frontendProcess.stdout.on('data', (data) => {
    console.log(`[frontend] ${data}`);
  });

  frontendProcess.stderr.on('data', (data) => {
    console.error(`[frontend] ${data}`);
  });

  return frontendProcess;
}

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 960,
    minHeight: 600,
    title: 'OfferGraph - 面经雷达',
    backgroundColor: '#18181b',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('http')) {
      shell.openExternal(url);
    }
    return { action: 'deny' };
  });

  const rendererUrl = `http://127.0.0.1:${FRONTEND_PORT}`;

  if (!isDev) {
    startBackend();
    startFrontend();
    await waitForServer(BACKEND_PORT);
    await waitForServer(FRONTEND_PORT);
  }

  await mainWindow.loadURL(rendererUrl);

  if (isDev) {
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  if (backendProcess) {
    backendProcess.kill();
    backendProcess = null;
  }
  if (frontendProcess) {
    frontendProcess.kill();
    frontendProcess = null;
  }
  app.quit();
});

app.on('activate', () => {
  if (mainWindow === null) {
    createWindow();
  }
});
