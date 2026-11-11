# Brain-Eleven kurulum ve güncelleme (Windows).
#   .\kur.ps1            bağımlılıkları kurar, hook'ları ve skill'leri yazar, doctor çalıştırır
#   .\kur.ps1 -Guncelle  önce master'ı hızlı ileri çeker (yerel değişiklik varsa durur), sonra aynısı
param([switch]$Guncelle)

$ErrorActionPreference = 'Stop'
$vault = $PSScriptRoot

function Calistir {
    & $args[0] $args[1..($args.Count - 1)]
    if ($LASTEXITCODE -ne 0) { throw "Komut başarısız oldu ($LASTEXITCODE): $args" }
}

if ($Guncelle) {
    # Yalnız izlenen dosyalar: vault notları (izlenmeyen) güncellemeyi engellemez.
    $degisen = git -C $vault status --porcelain --untracked-files=no
    if ($degisen) { throw "Yerel değişiklik var, güncelleme durdu:`n$($degisen -join "`n")" }
    $onceki = git -C $vault rev-parse HEAD
    Calistir git -C $vault checkout master
    Calistir git -C $vault pull --ff-only origin master
    Write-Host "Güncellendi: $onceki -> $(git -C $vault rev-parse HEAD)"
    Write-Host "Geri almak için: git -C `"$vault`" checkout $onceki ; .\kur.ps1"
}

Calistir python -m pip install -r (Join-Path $vault 'requirements.txt')
Calistir python -m brain_eleven --vault $vault install
Calistir python -m brain_eleven --vault $vault doctor
