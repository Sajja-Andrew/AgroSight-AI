# Single-command test runner for PowerShell.
# Usage: .\run_tests.ps1          # run all tests
#        .\run_tests.ps1 -m "not slow"  # skip slow tests
#        .\run_tests.ps1 -x            # stop on first failure

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir
pytest @args
