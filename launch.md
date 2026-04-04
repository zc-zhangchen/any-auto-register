# 启动与生效指南

## 启动

由于系统 pyenv 会拦截 conda，建议用绝对路径启动，确保使用正确的 Python 环境：

```bash
/opt/anaconda3/envs/any-auto-register/bin/python main.py
```

或者确认 conda activate 生效后再启动：

```bash
conda activate any-auto-register
which python  # 应输出 /opt/anaconda3/envs/any-auto-register/bin/python
python main.py
```

访问 http://localhost:8000

## 修改后端代码后生效

Ctrl+C 停掉当前后端，重新执行：

```bash
/opt/anaconda3/envs/any-auto-register/bin/python main.py
```

## 修改前端代码后生效

```bash
cd frontend && npm run build && cd ..
```

然后刷新浏览器。如果后端也改了，需要同时重启后端。

## 前端开发模式（热更新）

终端 1 启动后端，终端 2：

```bash
cd frontend && npm run dev
```

访问 http://localhost:5173，改前端代码会自动刷新，无需手动 build。
