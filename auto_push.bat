@echo off
powershell -ExecutionPolicy Bypass -File "%~dp0auto_push.ps1"
pause

# 设置最大重试次数
$maxRetries = 10
# 设置重试间隔（秒）
$retryInterval = 5
# 当前重试次数
$currentRetry = 0

Write-Host "开始尝试推送代码到GitHub..."
Write-Host "最大重试次数: $maxRetries"
Write-Host "重试间隔: $retryInterval 秒"

while ($currentRetry -lt $maxRetries) {
    $currentRetry++
    Write-Host "`n第 $currentRetry 次尝试..."
    
    try {
        # 尝试推送
        git push -u origin main
        Write-Host "推送成功！"
        exit 0
    } catch {
        Write-Host "推送失败: $($_.Exception.Message)"
        
        if ($currentRetry -lt $maxRetries) {
            Write-Host "等待 $retryInterval 秒后重试..."
            Start-Sleep -Seconds $retryInterval
        } else {
            Write-Host "`n达到最大重试次数，推送失败。"
            Write-Host "请检查以下可能的问题："
            Write-Host "1. 网络连接是否正常"
            Write-Host "2. GitHub服务器是否可访问"
            Write-Host "3. 代理设置是否正确"
            Write-Host "4. 防火墙是否阻止了连接"
            exit 1
        }
    }
}