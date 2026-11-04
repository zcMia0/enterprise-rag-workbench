# 一键启动脚本 (Windows / PowerShell)
# 用法: 在 enterprise-rag-workbench 目录下执行  .\scripts\start.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $root  # 回到项目根

Write-Host "==> 1) 启动基础设施 (Docker)" -ForegroundColor Cyan
docker compose up -d

Write-Host "==> 2) 启动后端 (:8000)" -ForegroundColor Cyan
Start-Process -FilePath "powershell" -ArgumentList "-NoExit","-Command","cd '$root/backend'; if(Test-Path venv){} else { python -m venv venv }; .\venv\Scripts\pip install -r requirements.txt; .\venv\Scripts\python -m uvicorn app.main:app --port 8000"

Write-Host "==> 3) 启动前端 (:5173)" -ForegroundColor Cyan
Start-Process -FilePath "powershell" -ArgumentList "-NoExit","-Command","cd '$root/frontend'; npm install; npm run dev"

Write-Host "==> 完成. 前端 http://localhost:5173  后端 http://localhost:8000/docs" -ForegroundColor Green
