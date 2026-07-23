#版本与更新检查模块
#只依赖标准库（urllib），不依赖 PySide6，方便单独测试，和 packs/ 保持一致。
#通过 GitHub Releases API 查询最新发布版本，与本地 VERSION 做语义化版本比较。
#
#防降级：只有当远端版本严格大于本地版本时才视为"有更新"。
#远端版本小于或等于本地时一律报告"已是最新"，绝不提示降级。
#查询失败（无网络、API 限流、解析失败）也不抛异常，只返回 has_update=False 并附说明。

import json
import os
import sys
import shutil
import tempfile
import zipfile
import urllib.request
import urllib.error
import hashlib
import re
import stat
import struct
import urllib.parse
import uuid

try:
    from src.packs.file_lock import template_write_lock, template_mutex_name
except ModuleNotFoundError:
    template_write_lock = None
    template_mutex_name = None

VERSION = "2.3.1"                      #当前版本（语义化，无前缀 v）；发布新版本时务必同步更新
REPO = "LUODIAN-233/Magia_Exedra_auto"
RELEASES_API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_LIST_API = f"https://api.github.com/repos/{REPO}/releases"  #所有 release（含预发布），beta 通道用
TAGS_API = f"https://api.github.com/repos/{REPO}/tags"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
TIMEOUT = 10                          #网络请求超时（秒），无网络时最多卡这么久，不阻塞 GUI
MAX_DOWNLOAD_BYTES = 512 * 1024 * 1024
MAX_EXTRACTED_BYTES = 2 * 1024 * 1024 * 1024
MAX_EXTRACTED_FILES = 20000
MAX_COMPRESSION_RATIO = 200
UPDATE_MANIFEST = ".update-manifest.json"


def parse_version(s):
    #把 "v2.1.0" / "2.1.0" / "v2.2.0-beta.1" 解析成可比较的元组：
    #  (major, minor, patch, is_release, pre_keys)
    #is_release=1 表示正式版（无预发布后缀），is_release=0 表示预发布（beta 等）。
    #同 major.minor.patch 下正式版 > 预发布；预发布间按 semver 规则比较（数值项 < 字符串项）。
    #无法解析返回 None。
    if not s:
        return None
    match = re.fullmatch(
        r'[vV]?(0|[1-9]\d*)\.(0|[1-9]\d*)(?:\.(0|[1-9]\d*))?'
        r'(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?'
        r'(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?',
        s.strip(),
    )
    if not match:
        return None
    major, minor, patch = int(match[1]), int(match[2]), int(match[3] or 0)
    pre = match[4] or ''
    if pre:
        pre_keys = []
        for p in pre.split('.'):
            if p.isdigit():
                if len(p) > 1 and p.startswith('0'):
                    return None
                pre_keys.append((0, int(p), ''))   #数值项：排在字符串项前
            else:
                pre_keys.append((1, 0, p))
        return (major, minor, patch, 0, tuple(pre_keys))
    return (major, minor, patch, 1, ())


def _fetch_json(url, timeout=TIMEOUT):
    #GET 一个 JSON 接口；GitHub API 要求带 User-Agent，否则返回 403
    req = urllib.request.Request(url, headers={'User-Agent': f'magia-exedra-auto/{VERSION}'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _fetch_pages(url, timeout=TIMEOUT, max_pages=20, is_cancelled=None):
    items = []
    separator = '&' if '?' in url else '?'
    for page in range(1, max_pages + 1):
        if is_cancelled and is_cancelled():
            raise UpdateCancelled('更新检查已取消')
        batch = _fetch_json(f'{url}{separator}per_page=100&page={page}', timeout)
        if is_cancelled and is_cancelled():
            raise UpdateCancelled('更新检查已取消')
        if not isinstance(batch, list):
            raise ValueError('GitHub API 返回格式无效')
        items.extend(batch)
        if len(batch) < 100:
            return items
    raise ValueError('GitHub 版本列表超过安全分页上限')


def check_for_update(current=VERSION, channel='stable', timeout=TIMEOUT, is_cancelled=None):
    #查询 GitHub 最新版本并与 current 比较。
    #channel='stable'（默认）：只看正式 release（releases/latest 已排除预发布），不会提示 beta。
    #channel='beta'：看所有 release（含预发布），选 semver 最大的，可能含 beta。
    #防降级：只有远端严格大于本地才提示更新；预发布版本按 semver 比较（正式版 > 同版本预发布）。
    #任何网络/解析错误都不抛出，返回 has_update=False 并附 message。
    result = {
        'current': current,
        'latest': None,
        'latest_tag': None,
        'has_update': False,
        'url': RELEASES_PAGE,
        'asset_url': None,
        'asset_name': None,
        'asset_size': 0,
        'asset_sha256': None,
        'channel': channel,
        'message': '',
    }
    cur = parse_version(current)
    if cur is None:
        result['message'] = f'本地版本号无法解析：{current}，跳过更新检查。'
        return result

    tag = None
    url = RELEASES_PAGE
    asset = None

    if channel == 'beta':
        #beta 通道：取所有 release（含预发布），选 semver 最大的
        try:
            releases = _fetch_pages(RELEASES_LIST_API, timeout, is_cancelled=is_cancelled)
            best_ver = None
            for rel in releases:
                t = rel.get('tag_name', '')
                v = parse_version(t)
                if v is None:
                    continue
                if best_ver is None or v > best_ver:
                    best_ver = v
                    tag = t
                    if rel.get('html_url'):
                        url = rel['html_url']
                    asset = find_asset(rel, t)
        except Exception as e:
            result['message'] = f'查询更新失败：{e}'
            return result
    else:
        #稳定通道：releases/latest 已排除预发布
        try:
            if is_cancelled and is_cancelled():
                raise UpdateCancelled('更新检查已取消')
            data = _fetch_json(RELEASES_API, timeout)
            tag = data.get('tag_name')
            if data.get('html_url'):
                url = data['html_url']
            asset = find_asset(data, tag)
        except urllib.error.HTTPError as e:
            if e.code != 404:            #404 表示还没有 release，回退到 tags
                result['message'] = f'查询更新失败（HTTP {e.code}）。'
                return result
        except Exception as e:
            result['message'] = f'查询更新失败：{e}'
            return result

    #没有 release 时回退到 tags，取 semver 最大的（无 asset）。稳定通道跳过预发布标签。
    if not tag:
        try:
            tags = _fetch_pages(TAGS_API, timeout, is_cancelled=is_cancelled)
            best_ver = None
            for item in tags:
                name = item.get('name', '')
                v = parse_version(name)
                if v is None:
                    continue
                if channel != 'beta' and v[3] == 0:
                    continue
                if best_ver is None or v > best_ver:
                    best_ver = v
                    tag = name
            if tag:
                url = f"https://github.com/{REPO}/releases/tag/{tag}"
        except Exception as e:
            result['message'] = f'查询更新失败：{e}'
            return result

    if not tag:
        result['message'] = '未找到任何版本标签，跳过更新检查。'
        return result

    latest = parse_version(tag)
    result['latest_tag'] = tag
    result['latest'] = tag.lstrip('vV')
    result['url'] = url
    if asset:
        result['asset_name'] = asset['name']
        result['asset_size'] = asset['size']
        result['asset_url'] = asset['url']
        result['asset_sha256'] = asset['sha256']

    if latest is None:
        result['message'] = f'远端版本号无法解析：{tag}，跳过更新检查。'
        return result

    #防降级：只有远端严格大于本地才提示更新。展示时本地版本统一加 v 前缀，与远端 tag 一致
    local_disp = current if current[:1] in ('v', 'V') else f'v{current}'
    if latest > cur:
        result['has_update'] = True
        result['message'] = f'发现新版本：{tag}（当前 {local_disp}）。前往 {url} 查看。'
    else:
        result['has_update'] = False
        result['message'] = f'当前已是最新版本（当前 {local_disp}，远端 {tag}）。'
    return result


#-----------打包版自动更新辅助-----------
#仅用于 PyInstaller 打包后的 exe 运行模式：下载 release 里的更新包 zip，解压到临时目录，
#再写一个批处理在主进程退出后用 robocopy 覆盖安装目录并重启。
#源码运行模式不走这条路径（由 GUI 侧回退为打开 Release 页）。

def is_frozen():
    #是否以 PyInstaller 打包后的 exe 运行
    return getattr(sys, 'frozen', False)


def find_asset(release_data, expected_tag=None):
    #只接受唯一、上传完成、有 GitHub SHA-256 的约定 ZIP；不再把任意附件当更新包。
    assets = release_data.get('assets', []) if isinstance(release_data, dict) else []
    matches = []
    for a in assets:
        name = a.get('name', '')
        size = a.get('size')
        url = a.get('browser_download_url')
        digest = a.get('digest', '')
        parsed = urllib.parse.urlparse(url or '')
        if not re.fullmatch(r'MagiaExedra_auto_[A-Za-z0-9._-]+\.zip', name, re.IGNORECASE):
            continue
        if expected_tag:
            allowed_names = {
                f'MagiaExedra_auto_{expected_tag}.zip'.casefold(),
                f'MagiaExedra_auto_{expected_tag}_win64.zip'.casefold(),
            }
            if name.casefold() not in allowed_names:
                continue
        if a.get('state') not in (None, 'uploaded') or not isinstance(size, int) \
                or not 0 < size <= MAX_DOWNLOAD_BYTES:
            continue
        if parsed.scheme != 'https' or parsed.hostname != 'github.com':
            continue
        expected_prefix = f'/{REPO}/releases/download/'
        if not urllib.parse.unquote(parsed.path).startswith(expected_prefix):
            continue
        if not isinstance(digest, str) or not re.fullmatch(r'sha256:[0-9a-fA-F]{64}', digest):
            continue
        matches.append({'name': name, 'size': size, 'url': url, 'sha256': digest.split(':', 1)[1].lower()})
    return matches[0] if len(matches) == 1 else None


class UpdateCancelled(Exception):
    pass


def download_asset(url, dest_path, expected_size, expected_sha256, progress_cb=None,
                   is_cancelled=None, timeout=10):
    #下载到 .part，大小和 SHA-256 都通过后才原子提交。
    if not isinstance(expected_size, int) or not 0 < expected_size <= MAX_DOWNLOAD_BYTES:
        raise ValueError('更新包大小无效')
    if not re.fullmatch(r'[0-9a-fA-F]{64}', expected_sha256 or ''):
        raise ValueError('更新包缺少可信 SHA-256')
    part_path = dest_path + '.part'
    req = urllib.request.Request(url, headers={'User-Agent': f'magia-exedra-auto/{VERSION}'})
    digest = hashlib.sha256()
    done = 0
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            final = urllib.parse.urlparse(resp.geturl())
            host = (final.hostname or '').lower()
            if final.scheme != 'https' or not (host == 'github.com' or host.endswith('.githubusercontent.com')):
                raise ValueError('更新下载被重定向到不受信任的地址')
            encoding = resp.headers.get('Content-Encoding', 'identity').lower()
            if encoding not in ('', 'identity'):
                raise ValueError('更新服务器返回了不支持的压缩编码')
            length = int(resp.headers.get('Content-Length') or 0)
            if length and length != expected_size:
                raise ValueError('更新包响应大小与 Release 信息不一致')
            with open(part_path, 'xb') as f:
                while True:
                    if is_cancelled and is_cancelled():
                        raise UpdateCancelled('更新下载已取消')
                    chunk = resp.read(256 * 1024)
                    if not chunk:
                        break
                    done += len(chunk)
                    if done > expected_size or done > MAX_DOWNLOAD_BYTES:
                        raise ValueError('更新包超过预期大小')
                    f.write(chunk)
                    digest.update(chunk)
                    if progress_cb:
                        progress_cb(done, expected_size)
                f.flush()
                os.fsync(f.fileno())
        if done != expected_size:
            raise ValueError('更新包下载不完整')
        if digest.hexdigest().lower() != expected_sha256.lower():
            raise ValueError('更新包 SHA-256 校验失败')
        os.replace(part_path, dest_path)
    finally:
        if os.path.exists(part_path):
            os.remove(part_path)
    return dest_path


def _safe_zip_name(name):
    if not isinstance(name, str) or not name or '\\' in name or '\x00' in name:
        return None
    if name.startswith('/') or re.match(r'^[A-Za-z]:', name):
        return None
    parts = name.rstrip('/').split('/')
    reserved = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}
    if not parts or any(not p or p in ('.', '..') or ':' in p or p.endswith((' ', '.'))
                        or p.split('.', 1)[0].upper() in reserved for p in parts):
        return None
    return parts


def _validate_pe(path):
    with open(path, 'rb') as f:
        header = f.read(64)
        if len(header) < 64 or header[:2] != b'MZ':
            return False
        pe_offset = struct.unpack_from('<I', header, 0x3c)[0]
        f.seek(pe_offset)
        pe = f.read(6)
    return len(pe) == 6 and pe[:4] == b'PE\0\0' and struct.unpack('<H', pe[4:])[0] == 0x8664


def extract_update(zip_path, staging_dir, expected_version, is_cancelled=None):
    #逐项安全解压，限制路径、类型、数量、体积和压缩比，并生成受管文件清单。
    if os.path.lexists(staging_dir):
        raise ValueError('更新解压目录必须是新的空目录')
    os.makedirs(staging_dir)
    seen = {}
    file_paths = []
    total_size = 0
    try:
        with zipfile.ZipFile(zip_path) as z:
            infos = z.infolist()
            if len(infos) > MAX_EXTRACTED_FILES:
                raise ValueError('更新包文件数量过多')
            for info in infos:
                if is_cancelled and is_cancelled():
                    raise UpdateCancelled('更新解压已取消')
                parts = _safe_zip_name(info.filename)
                if parts is None:
                    raise ValueError(f'更新包包含不安全路径: {info.filename!r}')
                key = '/'.join(parts).casefold()
                if key in seen:
                    raise ValueError(f'更新包包含重复路径: {info.filename}')
                for index in range(1, len(parts)):
                    parent_key = '/'.join(parts[:index]).casefold()
                    if seen.get(parent_key) == 'file':
                        raise ValueError(f'更新包包含文件/目录冲突: {info.filename}')
                is_dir = info.is_dir() or info.filename.endswith('/')
                prefix = key + '/'
                if not is_dir and any(existing.startswith(prefix) for existing in seen):
                    raise ValueError(f'更新包包含文件/目录冲突: {info.filename}')
                seen[key] = 'dir' if is_dir else 'file'
                mode = (info.external_attr >> 16) & 0xffff
                file_type = stat.S_IFMT(mode)
                if file_type not in (0, stat.S_IFREG, stat.S_IFDIR):
                    raise ValueError(f'更新包包含链接或特殊文件: {info.filename}')
                if info.flag_bits & 0x1:
                    raise ValueError('不支持加密更新包')
                total_size += info.file_size
                if total_size > MAX_EXTRACTED_BYTES:
                    raise ValueError('更新包解压后体积过大')
                if info.file_size and (not info.compress_size
                        or info.file_size / info.compress_size > MAX_COMPRESSION_RATIO):
                    raise ValueError('更新包压缩比异常')
                target = os.path.abspath(os.path.join(staging_dir, *parts))
                if os.path.commonpath((target, os.path.abspath(staging_dir))) != os.path.abspath(staging_dir):
                    raise ValueError('更新路径越出解压目录')
                if is_dir:
                    os.makedirs(target, exist_ok=True)
                    continue
                os.makedirs(os.path.dirname(target), exist_ok=True)
                written = 0
                with z.open(info) as src, open(target, 'xb') as dst:
                    while True:
                        if is_cancelled and is_cancelled():
                            raise UpdateCancelled('更新解压已取消')
                        chunk = src.read(256 * 1024)
                        if not chunk:
                            break
                        written += len(chunk)
                        if written > info.file_size:
                            raise ValueError('更新包条目大小异常')
                        dst.write(chunk)
                if written != info.file_size:
                    raise ValueError('更新包条目不完整')
                file_paths.append(target)
        roots = {os.path.relpath(p, staging_dir).split(os.sep, 1)[0] for p in file_paths}
        #入口 exe：优先项目名 Magia_Exedra_auto.exe，回退 main.exe（兼容旧版更新包）
        direct_main = os.path.join(staging_dir, 'Magia_Exedra_auto.exe')
        if not os.path.isfile(direct_main):
            direct_main = os.path.join(staging_dir, 'main.exe')
        if os.path.isfile(direct_main):
            release_root = staging_dir
        elif len(roots) == 1:
            release_root = os.path.join(staging_dir, next(iter(roots)))
        else:
            raise ValueError('更新包目录结构无效')
        main_exe = os.path.join(release_root, 'Magia_Exedra_auto.exe')
        if not os.path.isfile(main_exe):
            main_exe = os.path.join(release_root, 'main.exe')
        if not os.path.isfile(main_exe) or not _validate_pe(main_exe):
            raise ValueError('更新包缺少有效的可执行文件')
        manifest = {}
        for path in file_paths:
            if os.path.commonpath((os.path.abspath(path), os.path.abspath(release_root))) != os.path.abspath(release_root):
                raise ValueError('更新包包装目录之外包含文件')
            rel = os.path.relpath(path, release_root).replace(os.sep, '/')
            digest = hashlib.sha256()
            with open(path, 'rb') as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b''):
                    digest.update(chunk)
            manifest[rel] = {'size': os.path.getsize(path), 'sha256': digest.hexdigest()}
        manifest_path = os.path.join(release_root, UPDATE_MANIFEST)
        if parse_version(expected_version) is None:
            raise ValueError('目标更新版本无效')
        with open(manifest_path, 'x', encoding='utf-8') as f:
            json.dump({'schema': 1, 'version': expected_version.lstrip('vV'), 'files': manifest},
                      f, indent=2, sort_keys=True)
        return release_root
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise


def write_update_bat(exe_path, src_dir, pid, job_dir, lock_path, job_id):
    #生成唯一 PowerShell 安装器：检查 robocopy、校验文件、清理旧受管文件，失败时不重启。
    install_dir = os.path.dirname(exe_path)
    #新版本入口 exe 名：优先项目名，回退 main.exe（兼容旧版更新包）
    new_exe_name = 'Magia_Exedra_auto.exe'
    if not os.path.isfile(os.path.join(src_dir, new_exe_name)):
        new_exe_name = 'main.exe'
    token = uuid.uuid4().hex
    bat_path = os.path.join(job_dir, f'updater_{token}.bat')
    ps_path = os.path.join(job_dir, f'updater_{token}.ps1')
    config_path = os.path.join(job_dir, f'updater_{token}.json')
    log_path = os.path.join(job_dir, 'updater.log')
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump({'exe': exe_path, 'new_exe': new_exe_name, 'src': src_dir, 'dest': install_dir, 'pid': pid,
                   'job': job_dir, 'log': log_path, 'lock': lock_path, 'job_id': job_id,
                   'mutex': template_mutex_name(install_dir)},
                  f, ensure_ascii=False)
    #主程序仍持有更新锁时先落标记，堵住主进程退出到安装器接管之间的竞态窗口。
    with open(os.path.join(job_dir, 'INSTALL_IN_PROGRESS'), 'x', encoding='ascii') as f:
        f.write('installing')
    ps = r'''$ErrorActionPreference = 'Stop'
$c = Get-Content -LiteralPath $args[0] -Raw -Encoding UTF8 | ConvertFrom-Json
$newManifest = $null
$oldManifest = $null
$backup = $null
$existing = @{}
$hadOldManifest = $false
$templateMutex = $null
$mutexAcquired = $false
$backupHashes = @{}
$recoveryRequired = $false
function Get-SafePath([string]$root, [string]$relative) {
  if ([string]::IsNullOrWhiteSpace($relative) -or [IO.Path]::IsPathRooted($relative) -or
      $relative.Contains(':') -or $relative -match '(^|[\\/])\.\.([\\/]|$)') {
    throw "更新清单包含不安全路径: $relative"
  }
  $rootFull = [IO.Path]::GetFullPath($root).TrimEnd('\') + '\'
  $full = [IO.Path]::GetFullPath([IO.Path]::Combine($root, $relative.Replace('/', '\')))
  if (-not $full.StartsWith($rootFull, [StringComparison]::OrdinalIgnoreCase)) {
    throw "更新清单路径越界: $relative"
  }
  return $full
}
try {
  Add-Content -LiteralPath $c.log -Value "[$(Get-Date -Format o)] 更新开始"
  $templateMutex = New-Object System.Threading.Mutex($false, [string]$c.mutex)
  try {
    $mutexAcquired = $templateMutex.WaitOne([TimeSpan]::FromSeconds(60))
  } catch [System.Threading.AbandonedMutexException] {
    $mutexAcquired = $true
  }
  if (-not $mutexAcquired) { throw '等待其它实例释放模板租约超时' }
  if ($c.lock) {
    $lockTemp = "$($c.lock).$PID.tmp"
    @{ job_id = $c.job_id; pid = $PID; created = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds(); job = $c.job } |
      ConvertTo-Json -Compress | Set-Content -LiteralPath $lockTemp -Encoding UTF8
    Move-Item -LiteralPath $lockTemp -Destination $c.lock -Force
  }
  try { Wait-Process -Id ([int]$c.pid) -Timeout 60 -ErrorAction Stop } catch {
    if (Get-Process -Id ([int]$c.pid) -ErrorAction SilentlyContinue) { throw '等待主程序退出超时' }
  }
  $newManifestPath = Join-Path $c.src '.update-manifest.json'
  $newManifest = Get-Content -LiteralPath $newManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
  $oldManifestPath = Join-Path $c.dest '.update-manifest.json'
  $backup = Join-Path $c.job 'backup'
  New-Item -ItemType Directory -Path $backup -Force | Out-Null
  if (Test-Path -LiteralPath $oldManifestPath -PathType Leaf) {
    $hadOldManifest = $true
    Copy-Item -LiteralPath $oldManifestPath -Destination (Join-Path $backup '.update-manifest.json') -Force
    $oldManifest = Get-Content -LiteralPath $oldManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
  }
  $existing = @{}
  foreach ($p in $newManifest.files.PSObject.Properties) {
    $target = Get-SafePath $c.dest $p.Name
    if (Test-Path -LiteralPath $target -PathType Leaf) {
      $copy = Get-SafePath $backup $p.Name
      New-Item -ItemType Directory -Path (Split-Path -Parent $copy) -Force | Out-Null
      $copyTemp = "$copy.$PID.tmp"
      Copy-Item -LiteralPath $target -Destination $copyTemp -Force
      $copyHash = (Get-FileHash -LiteralPath $copyTemp -Algorithm SHA256).Hash.ToLowerInvariant()
      Move-Item -LiteralPath $copyTemp -Destination $copy -Force
      $existing[$p.Name] = $true
      $backupHashes[$p.Name] = $copyHash
    }
  }
  if ($oldManifest) {
    foreach ($p in $oldManifest.files.PSObject.Properties) {
      $target = Get-SafePath $c.dest $p.Name
      $copy = Get-SafePath $backup $p.Name
      if ((Test-Path -LiteralPath $target -PathType Leaf) -and -not (Test-Path -LiteralPath $copy)) {
        New-Item -ItemType Directory -Path (Split-Path -Parent $copy) -Force | Out-Null
        $copyTemp = "$copy.$PID.tmp"
        Copy-Item -LiteralPath $target -Destination $copyTemp -Force
        $copyHash = (Get-FileHash -LiteralPath $copyTemp -Algorithm SHA256).Hash.ToLowerInvariant()
        Move-Item -LiteralPath $copyTemp -Destination $copy -Force
        $backupHashes[$p.Name] = $copyHash
      }
    }
  }
  & robocopy $c.src $c.dest /E /COPY:DAT /DCOPY:DAT /R:2 /W:1 /XJ /NFL /NDL /NJH /NJS
  $rc = $LASTEXITCODE
  if ($rc -ge 8) { throw "robocopy 失败，返回码 $rc" }
  foreach ($p in $newManifest.files.PSObject.Properties) {
    $target = Get-SafePath $c.dest $p.Name
    if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { throw "更新文件缺失: $($p.Name)" }
    $hash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($hash -ne $p.Value.sha256) { throw "更新文件校验失败: $($p.Name)" }
  }
  if ($oldManifest) {
    $newNames = @{}; foreach ($p in $newManifest.files.PSObject.Properties) { $newNames[$p.Name] = $true }
    foreach ($p in $oldManifest.files.PSObject.Properties) {
      if (-not $newNames.ContainsKey($p.Name)) {
        $target = Get-SafePath $c.dest $p.Name
        if (Test-Path -LiteralPath $target -PathType Leaf) {
          $hash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
          if ($hash -eq $p.Value.sha256) { Remove-Item -LiteralPath $target -Force }
        }
      }
    }
  }
  $health = Join-Path $c.job 'startup-health'
  $env:MAGIA_UPDATE_HEALTH = $health
  $newExe = Join-Path $c.dest $c.new_exe
  $child = Start-Process -FilePath $newExe -WorkingDirectory $c.dest -PassThru
  $healthy = $false
  for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Milliseconds 500
    if (Test-Path -LiteralPath $health -PathType Leaf) { $healthy = $true; break }
    if ($child.HasExited) { break }
  }
  if (-not $healthy) {
    if (-not $child.HasExited) { Stop-Process -Id $child.Id -Force -ErrorAction SilentlyContinue }
    throw '新版本未能完成启动健康检查'
  }
  Remove-Item -LiteralPath (Join-Path $c.job 'INSTALL_IN_PROGRESS') -Force
  Set-Content -LiteralPath (Join-Path $c.job 'update-success') -Value 'ok' -Encoding ASCII
} catch {
  Add-Content -LiteralPath $c.log -Value $_
  if ($child -and -not $child.HasExited) { Stop-Process -Id $child.Id -Force -ErrorAction SilentlyContinue }
  $rollbackErrors = New-Object System.Collections.Generic.List[string]
  if ($newManifest) {
    foreach ($p in $newManifest.files.PSObject.Properties) {
      try {
        $target = Get-SafePath $c.dest $p.Name
        $copy = Get-SafePath $backup $p.Name
        if (Test-Path -LiteralPath $copy -PathType Leaf) {
          New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
          Copy-Item -LiteralPath $copy -Destination $target -Force
          $restored = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
          if ($backupHashes.ContainsKey($p.Name) -and $restored -ne $backupHashes[$p.Name]) { throw '恢复后哈希不一致' }
        } elseif (-not $existing.ContainsKey($p.Name) -and (Test-Path -LiteralPath $target -PathType Leaf)) {
          Remove-Item -LiteralPath $target -Force
        }
      } catch { $rollbackErrors.Add("$($p.Name): $($_.Exception.Message)") }
    }
  }
  if ($oldManifest) {
    foreach ($p in $oldManifest.files.PSObject.Properties) {
      try {
        $target = Get-SafePath $c.dest $p.Name
        $copy = Get-SafePath $backup $p.Name
        if (Test-Path -LiteralPath $copy -PathType Leaf) {
          New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
          Copy-Item -LiteralPath $copy -Destination $target -Force
          $restored = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
          if ($backupHashes.ContainsKey($p.Name) -and $restored -ne $backupHashes[$p.Name]) { throw '恢复后哈希不一致' }
        }
      } catch { $rollbackErrors.Add("$($p.Name): $($_.Exception.Message)") }
    }
  }
  try {
    $installedManifest = Join-Path $c.dest '.update-manifest.json'
    $oldManifestBackup = Join-Path $backup '.update-manifest.json'
    if ($hadOldManifest -and (Test-Path -LiteralPath $oldManifestBackup -PathType Leaf)) {
      Copy-Item -LiteralPath $oldManifestBackup -Destination $installedManifest -Force
    } elseif (-not $hadOldManifest -and (Test-Path -LiteralPath $installedManifest -PathType Leaf)) {
      Remove-Item -LiteralPath $installedManifest -Force
    }
  } catch { $rollbackErrors.Add("manifest: $($_.Exception.Message)") }
  if ($rollbackErrors.Count -gt 0) {
    $recoveryRequired = $true
    Set-Content -LiteralPath (Join-Path $c.job 'RECOVERY_REQUIRED.txt') -Value ($rollbackErrors -join "`r`n") -Encoding UTF8
    Add-Content -LiteralPath $c.log -Value ('回滚不完整: ' + ($rollbackErrors -join '; '))
  } else {
    Remove-Item -LiteralPath (Join-Path $c.job 'INSTALL_IN_PROGRESS') -Force -ErrorAction SilentlyContinue
  }
} finally {
  if ($mutexAcquired -and $templateMutex) { $templateMutex.ReleaseMutex() }
  if ($templateMutex) { $templateMutex.Dispose() }
  if ($c.lock -and -not $recoveryRequired) { Remove-Item -LiteralPath $c.lock -Force -ErrorAction SilentlyContinue }
}
'''
    with open(ps_path, 'w', encoding='utf-8-sig') as f:
        f.write(ps)
    ps_name = os.path.basename(ps_path)
    config_name = os.path.basename(config_path)
    content = (f'@echo off\r\n'
               f'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0{ps_name}" "%~dp0{config_name}"\r\n'
               f'if exist "%~dp0update-success" ('
               f' start "" /b cmd /c "ping -n 3 127.0.0.1 ^>nul ^& rmdir /s /q ^"%~dp0^"" )\r\n')
    with open(bat_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return bat_path


def acquire_update_lock(install_dir, job_id, job_dir):
    #文件锁覆盖不同 Windows session；同一安装目录同一时间只允许一个自动更新任务。
    identity = os.path.normcase(os.path.realpath(install_dir)).encode('utf-8')
    lock_root = os.path.join(tempfile.gettempdir(), 'magia_exedra_update_locks')
    os.makedirs(lock_root, exist_ok=True)
    lock_path = os.path.join(lock_root, hashlib.sha256(identity).hexdigest() + '.lock')
    payload = json.dumps({'job_id': job_id, 'pid': os.getpid(), 'created': __import__('time').time(),
                          'job': job_dir})
    def _acquire_file():
        try:
            return os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                with open(lock_path, 'r', encoding='utf-8-sig') as f:
                    old = json.load(f)
                pid = int(old.get('pid', 0))
                old_job = old.get('job') or ''
                recovery = os.path.join(old_job, 'RECOVERY_REQUIRED.txt')
                in_progress = os.path.join(old_job, 'INSTALL_IN_PROGRESS')
                if old_job and (os.path.isfile(recovery) or os.path.isfile(in_progress)):
                    marker = recovery if os.path.isfile(recovery) else in_progress
                    raise RuntimeError(f'检测到上次更新未安全完成，请先检查恢复目录: {marker}')
                import ctypes
                kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
                kernel32.OpenProcess.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32)
                kernel32.OpenProcess.restype = ctypes.c_void_p
                kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
                ctypes.set_last_error(0)
                handle = kernel32.OpenProcess(0x1000, False, pid) if pid > 0 else 0
                last_error = ctypes.get_last_error()
                alive = bool(handle) or last_error != 87
                if handle:
                    kernel32.CloseHandle(handle)
                if alive:
                    raise RuntimeError('另一个程序实例正在准备更新')
                os.remove(lock_path)
                return os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except RuntimeError:
                raise
            except Exception as e:
                #已持有同安装目录 mutex，损坏元数据不可能属于仍在运行的合规 updater。
                try:
                    os.remove(lock_path)
                    return os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                except OSError as cleanup_error:
                    raise RuntimeError(f'无法恢复损坏的更新锁: {cleanup_error}') from e
    if template_write_lock is not None:
        with template_write_lock(install_dir, timeout=2):
            fd = _acquire_file()
    else:
        fd = _acquire_file()
    try:
        with os.fdopen(fd, 'w', encoding='ascii') as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
    except Exception:
        try:
            os.remove(lock_path)
        except OSError:
            pass
        raise
    return lock_path


def release_update_lock(lock_path, job_id):
    if not lock_path:
        return
    try:
        with open(lock_path, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)
        if data.get('job_id') == job_id:
            os.remove(lock_path)
    except (OSError, ValueError, TypeError):
        pass


def update_recovery_issue(install_dir):
    identity = os.path.normcase(os.path.realpath(install_dir)).encode('utf-8')
    lock_path = os.path.join(
        tempfile.gettempdir(), 'magia_exedra_update_locks', hashlib.sha256(identity).hexdigest() + '.lock',
    )
    try:
        with open(lock_path, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)
        job_dir = data.get('job') or ''
        for name in ('RECOVERY_REQUIRED.txt', 'INSTALL_IN_PROGRESS'):
            marker = os.path.join(job_dir, name)
            if job_dir and os.path.isfile(marker):
                return marker
    except (OSError, ValueError, TypeError):
        return None
    return None


if __name__ == '__main__':
    #单独运行时分别按 stable / beta 通道各查一次，方便排查
    print('VERSION:', VERSION)
    for ch in ('stable', 'beta'):
        print(f'--- channel={ch} ---')
        r = check_for_update(channel=ch)
        for k, v in r.items():
            print(f'{k}: {v}')
