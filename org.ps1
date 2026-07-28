param(
    [string]$add = '',
    [string]$folder = '',
    [string]$pattern = 'y-m-d',
    [switch]$flatten
)

if($add -eq '' -and $folder -eq '' -and !$flatten){
    Write-Host @"

ORGANIZE.PS1 HELP

-add     (date prefix) created | mod | title
-folder  y | y\m | y\q | y-m-d  (use quotes: "y\q")
-pattern y-m-d | y-m | y  (only with -add title)
-flatten (no value - runs alone)

EXAMPLES:
  .\org.ps1 -add created
  .\org.ps1 -add mod
  .\org.ps1 -add title
  .\org.ps1 -folder y
  .\org.ps1 -folder "y\q"
  .\org.ps1 -flatten

"@
    exit
}

$s = $MyInvocation.MyCommand.Name

if($flatten){
    Get-ChildItem -File -Recurse -ErrorAction SilentlyContinue | Where-Object {$_.DirectoryName -ne $pwd.Path -and $_.Name -ne $s} | ForEach-Object {
        $dest = "$pwd\$($_.Name)"
        $i = 1
        while(Test-Path $dest){
            $base = [IO.Path]::GetFileNameWithoutExtension($_.Name)
            $dest = "$pwd\$base-$i$($_.Extension)"
            $i++
        }
        Move-Item $_.FullName $dest -Force -ErrorAction SilentlyContinue
    }
    while($true){
        $empty = Get-ChildItem -Directory -Recurse -ErrorAction SilentlyContinue | Where-Object {!(Get-ChildItem $_ -Force -ErrorAction SilentlyContinue)}
        if(!$empty){break}
        $empty | Remove-Item -Force -ErrorAction SilentlyContinue
    }
    exit
}

if($add){
    Get-ChildItem -File -ErrorAction SilentlyContinue | Where-Object {$_.Name -ne $s} | ForEach-Object {
        $dt = $null
        if($add -eq 'title'){
            $regex = @{'y-m-d'='(\d{4})[-._]?(\d{2})[-._]?(\d{2})';'y-m'='(\d{4})[-._]?(\d{2})';'y'='(\d{4})'}[$pattern]
            if($regex){$m = [regex]::Matches($_.Name, $regex); if($m.Count -gt 0){$y=$m[0].Groups[1].Value; $mo=if($m[0].Groups[2].Success){$m[0].Groups[2].Value}else{''}; $d=if($m[0].Groups[3].Success){$m[0].Groups[3].Value}else{''}; $dt=if($mo -and $d){[datetime]"$y-$mo-$d"}elseif($mo){[datetime]"$y-$mo-01"}else{[datetime]"$y-01-01"}}}
        } elseif($add -eq 'mod'){$dt = $_.LastWriteTime} else {$dt = $_.CreationTime}
        if($dt){$prefix = $dt.ToString('yyyy-MM-dd'); $new = "$prefix $($_.Name)"; $i=1; while(Test-Path $new){$base=[IO.Path]::GetFileNameWithoutExtension($_.Name); $new="$prefix $base-$i$($_.Extension)"; $i++}; Rename-Item $_.FullName $new -Force -ErrorAction SilentlyContinue}
    }
}

if($folder){
    Get-ChildItem -ErrorAction SilentlyContinue | Where-Object {!($_.PSIsContainer -and $_.Name -match '^\d{4}$') -and $_.Name -ne $s} | ForEach-Object {
        $dt = if($add -eq 'title'){
            $regex = @{'y-m-d'='(\d{4})[-._]?(\d{2})[-._]?(\d{2})';'y-m'='(\d{4})[-._]?(\d{2})';'y'='(\d{4})'}[$pattern]
            if($regex){$m = [regex]::Matches($_.Name, $regex); if($m.Count -gt 0){$y=$m[0].Groups[1].Value; $mo=if($m[0].Groups[2].Success){$m[0].Groups[2].Value}else{''}; $d=if($m[0].Groups[3].Success){$m[0].Groups[3].Value}else{''}; if($mo -and $d){[datetime]"$y-$mo-$d"}elseif($mo){[datetime]"$y-$mo-01"}else{[datetime]"$y-01-01"}}}
        } elseif($add -eq 'mod'){$_.LastWriteTime} else {$_.CreationTime}
        if($dt){$path = $folder -replace 'y',$dt.Year -replace 'q',"q$([math]::Ceiling($dt.Month/3))" -replace 'm',$dt.ToString('MM') -replace 'd',$dt.ToString('dd'); $path = $path -replace '\\','\'; if(!(Test-Path $path)){New-Item $path -ItemType Directory -Force -ErrorAction SilentlyContinue | Out-Null}; Move-Item $_.FullName $path -Force -ErrorAction SilentlyContinue}
    }
}
