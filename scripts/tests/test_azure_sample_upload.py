import base64
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]


def test_sample_upload_is_idempotent_with_azure_cli_stub():
    script_path = ROOT / "deploy/azure/scripts/upload-sample-models.ps1"
    assert script_path.is_file(), "Azure sample-model upload helper is missing"
    script = r'''
$ErrorActionPreference = "Stop"
$global:blobs = @{}
function global:az {
    $global:LASTEXITCODE = 0
    $nameIndex = [Array]::IndexOf($args, '--name')
    $name = if ($nameIndex -ge 0) { [string]$args[$nameIndex + 1] } else { '' }
    if ($args[2] -eq 'exists') {
        return (@{ exists = $global:blobs.ContainsKey($name) } | ConvertTo-Json -Compress)
    }
    if ($args[2] -eq 'show') { return $global:blobs[$name] }
    if ($args[2] -eq 'upload') {
        if ($global:blobs.ContainsKey($name)) { throw 'unexpected overwrite' }
        $metadataIndex = [Array]::IndexOf($args, '--metadata')
        $global:blobs[$name] = ([string]$args[$metadataIndex + 1]).Substring(7)
        return
    }
    throw 'unexpected Azure CLI invocation'
}
& '__SCRIPT__' -StorageAccountName 'testaccount'
& '__SCRIPT__' -StorageAccountName 'testaccount'
if ($global:blobs.Count -ne 4) { throw 'expected four sample models' }
if (-not $global:blobs.ContainsKey('sample_models/男/mannequin-male-1.png')) { throw 'male model path missing' }
if (-not $global:blobs.ContainsKey('sample_models/女/mannequin-female-1.png')) { throw 'female model path missing' }
$global:blobs['sample_models/男/mannequin-male-1.png'] = 'incorrect'
$rejected = $false
try { & '__SCRIPT__' -StorageAccountName 'testaccount' } catch { $rejected = $true }
if (-not $rejected -or $global:blobs.Count -ne 4) { throw 'hash mismatch was not safely rejected' }
'''.replace("__SCRIPT__", str(script_path).replace("'", "''"))
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    result = subprocess.run(["pwsh", "-NoLogo", "-NoProfile", "-EncodedCommand", encoded],
                            cwd=ROOT, capture_output=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stderr
