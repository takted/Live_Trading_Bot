param(
    [string]$AwsRegion = $env:AWS_REGION,
    [string]$AwsAccountId = $env:AWS_ACCOUNT_ID,
    [string]$EcrRepository = "itrading-forex",
    [string]$ImageTag = "latest",
    [string]$LogGroupName = "/itrading/forex",
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

function Assert-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command not found: $Name"
    }
}

Assert-Command aws
Assert-Command docker

if (-not $AwsRegion) {
    $AwsRegion = "us-east-1"
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$dockerfile = Join-Path $repoRoot "deploy\aws\Dockerfile"
$manifestPath = Join-Path $repoRoot "deploy\aws\forex_schedule_manifest.json"

if (-not (Test-Path $dockerfile)) {
    throw "Dockerfile not found: $dockerfile"
}

if (-not (Test-Path $manifestPath)) {
    throw "Schedule manifest not found: $manifestPath"
}

if (-not $AwsAccountId) {
    $AwsAccountId = (aws sts get-caller-identity --query Account --output text).Trim()
}

if (-not $AwsAccountId) {
    throw "Could not determine AWS account ID."
}

$ecrUri = "$AwsAccountId.dkr.ecr.$AwsRegion.amazonaws.com/$EcrRepository"
$resolvedTag = if ($ImageTag) { $ImageTag } else { "latest" }
$localImage = "${EcrRepository}:$resolvedTag"
$remoteImage = "${ecrUri}:$resolvedTag"

Write-Host "Repo root: $repoRoot"
Write-Host "Region:    $AwsRegion"
Write-Host "ECR URI:   $ecrUri"

aws ecr describe-repositories --repository-names $EcrRepository --region $AwsRegion 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Creating ECR repository $EcrRepository..."
    aws ecr create-repository --repository-name $EcrRepository --region $AwsRegion | Out-Null
}

Write-Host "Logging Docker into ECR..."
aws ecr get-login-password --region $AwsRegion | docker login --username AWS --password-stdin $ecrUri

if (-not $SkipBuild) {
    Write-Host "Building Docker image..."
    docker build -f $dockerfile -t $localImage $repoRoot
}

Write-Host "Tagging image..."
docker tag $localImage $remoteImage

Write-Host "Pushing image..."
docker push $remoteImage

aws logs create-log-group --log-group-name $LogGroupName --region $AwsRegion 2>$null | Out-Null

$manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
Write-Host ""
Write-Host "Scheduled instruments:"
foreach ($item in $manifest.instruments) {
    Write-Host ("- {0} {1}-{2} | start {3} | stop {4}" -f $item.instrument, $item.start_time, $item.end_time, $item.start_cron, $item.stop_cron)
}

Write-Host ""
Write-Host "Next AWS console actions:"
Write-Host "1. Launch or verify the always-on EC2 instance."
Write-Host "2. Install IB Gateway/TWS and Docker on the instance."
Write-Host "3. Copy credentials to itrading/config/itrading_credentials.json on EC2."
Write-Host "4. Pull the ECR image on EC2 and start one container per instrument."
Write-Host "5. Create EventBridge Scheduler rules that call SSM Run Command to docker start/stop each container."
