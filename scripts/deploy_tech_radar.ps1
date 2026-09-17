param(
  [string]$HostName = "112.74.55.38",
  [string]$User = "root",
  [int]$Port = 53653,
  [string]$RemoteDir = "/opt/tech-radar"
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Package = Join-Path $env:TEMP "tech-radar-release.tar.gz"

Write-Host "[1/5] 打包项目 -> $Package"
if (Test-Path $Package) { Remove-Item $Package -Force }
Push-Location $Root
try {
  tar --exclude=.git --exclude=__pycache__ --exclude='*.pyc' --exclude='.pytest_cache' -czf $Package tech_radar reddit_proxy_pool config deploy requirements.txt README.md docs
} finally {
  Pop-Location
}

$Target = "$User@$HostName"
Write-Host "[2/5] 上传到 $Target"
scp -P $Port $Package "${Target}:/tmp/tech-radar-release.tar.gz"

Write-Host "[3/5] 远程安装依赖和 systemd 服务"
$RemoteScript = @"
set -euo pipefail
mkdir -p $RemoteDir /var/lib/tech-radar /var/lib/reddit-proxy-pool-runtime
rm -rf $RemoteDir/*
tar -xzf /tmp/tech-radar-release.tar.gz -C $RemoteDir --strip-components=0
cd $RemoteDir
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
cp deploy/tech-radar.service /etc/systemd/system/tech-radar.service
if [ -f deploy/reddit-proxy-monitor.service ]; then
  cp deploy/reddit-proxy-monitor.service /etc/systemd/system/reddit-proxy-monitor.service
fi
if command -v ufw >/dev/null 2>&1; then
  ufw allow 5080/tcp comment 'Tech Radar HTTP service' >/dev/null || true
fi
systemctl daemon-reload
if [ -d /opt/wzdnzd-aggregator ] && [ -f /etc/systemd/system/reddit-proxy-monitor.service ]; then
  systemctl enable reddit-proxy-monitor
  systemctl restart reddit-proxy-monitor || journalctl -u reddit-proxy-monitor -n 80 --no-pager
else
  echo "跳过 reddit-proxy-monitor：/opt/wzdnzd-aggregator 不存在或 service 未安装"
fi
systemctl enable tech-radar
systemctl restart tech-radar
"@
ssh -p $Port $Target $RemoteScript

Write-Host "[4/5] 查看服务状态"
ssh -p $Port $Target "systemctl --no-pager --full status tech-radar | sed -n '1,18p'"
ssh -p $Port $Target "systemctl --no-pager --full status reddit-proxy-monitor 2>/dev/null | sed -n '1,18p' || true"

Write-Host "[5/5] 健康检查"
Start-Sleep -Seconds 3
Invoke-WebRequest -UseBasicParsing "http://$HostName`:5080/health" -TimeoutSec 15 | Select-Object -ExpandProperty Content
Write-Host "部署完成: http://$HostName`:5080/"
