# OfferGraph AI 验证脚本
# 运行 PRD 同步检查和验证建议，然后执行后端测试

Write-Host "=" * 60
Write-Host "OfferGraph AI 验证"
Write-Host "=" * 60
Write-Host ""

# 1. PRD 同步检查
Write-Host "[1/3] 检查 PRD 同步..."
Write-Host ""
python scripts/ai_guards/check_prd_sync.py
$prdCheck = $LASTEXITCODE
Write-Host ""

if ($prdCheck -ne 0) {
    Write-Host "警告：PRD 同步检查未通过。请确认是否需要更新 PRD.md。" -ForegroundColor Yellow
    Write-Host ""
}

# 2. 验证建议
Write-Host "[2/3] 分析改动区域..."
Write-Host ""
python scripts/ai_guards/verify_touched_areas.py
Write-Host ""

# 3. 后端测试
if (Test-Path "backend") {
    Write-Host "[3/3] 运行后端测试..."
    Write-Host ""
    Push-Location backend
    pytest tests/ -v
    $testCode = $LASTEXITCODE
    Pop-Location

    if ($testCode -ne 0) {
        Write-Host ""
        Write-Host "错误：后端测试未通过。" -ForegroundColor Red
        exit $testCode
    }
} else {
    Write-Host "[3/3] 未找到 backend 目录，跳过后端测试。"
}

Write-Host ""
Write-Host "=" * 60

if ($prdCheck -ne 0) {
    Write-Host "结果：PRD 同步需要确认" -ForegroundColor Yellow
    exit 1
} else {
    Write-Host "结果：验证通过" -ForegroundColor Green
    exit 0
}
