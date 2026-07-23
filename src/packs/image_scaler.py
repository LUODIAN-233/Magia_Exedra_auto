#素材缩放模块
#把 language/<语言>/<语言>_2560x1440 里的 2K 模板按倍率缩放到其它分辨率的 pack。
#只依赖标准库，不依赖 PySide6，方便单独测试，和 language_switcher.py 保持一致。
#
#实际缩放用 tools/ImageMagick/magick.exe。便携版 magick 找不到 coder 模块时会报
#CoderModulesPath / no decode delegate，必须先把 MAGICK_HOME、模块路径、PATH 指向
#tools/ImageMagick 才能用，所以这里给子进程单独构造环境变量，不污染主进程。
#
#以 2K（2560x1440）为唯一标准源，向下/向上派生其它分辨率：
#  0.5x  → 1280x720  （下采样，质量好）
#  0.75x → 1920x1080 （下采样，质量好）
#  1.5x  → 3840x2160 （上采样，非整数倍，magick 重采样插值，模板略糊、匹配稳定性稍降）
#下采样的 720p/1080p pack 质量优于上采样的 4K pack，但总比空着没法用强。
#mogrify 的 -path 会把子目录拍平，破坏 <dirpath>_N.png 的分组结构，
#所以这里逐张用 magick convert，保留源 pack 的子目录结构写到目标 pack。
#
#目标不存在或比 2K 源旧时才生成，反复刷新不会重复处理，也不会遗留陈旧模板。

import os
import shutil
import sys
import stat
import subprocess
import hashlib
import json
import tempfile
import time
import re

try:
    from src.packs.file_lock import template_write_lock, TemplateOperationCancelled
except ModuleNotFoundError:  #支持直接运行本文件排查
    from file_lock import template_write_lock, TemplateOperationCancelled

SOURCE_RES = "2560x1440"   #2K 是唯一的标准源，所有缩放都从它派生
SOURCE_W = 2560
SOURCE_H = 1440
#和 image.bash 一致的扩展名
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp")
MANIFEST_NAME = ".source_hashes.json"
RECIPE_VERSION = 2
SCALE_FACTORS = {
    "1280x720": 0.5,
    "1920x1080": 0.75,
    "3840x2160": 1.5,
}


def base_dir():
    #脚本位于 src/packs/ 子目录，需再上两层到仓库根；打包后用可执行文件所在目录
    #与 language_switcher.py 的 base_dir 逻辑一致（与 main.py 仅非打包分支多上两层）
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


BASE_DIR = base_dir()
LANGUAGE_DIR = os.path.join(BASE_DIR, "language")
MAGICK_EXE = os.path.join(BASE_DIR, "tools", "ImageMagick", "magick.exe")


#-----------基础工具-----------

def _magick_cmd():
    """
    返回 (命令前缀列表, 子进程环境变量)。
    优先用打包进 tools/ 的 magick.exe（并配好便携版必需的环境变量）；
    找不到就退回到 PATH 里的 magick，环境变量不改（系统安装版自己能跑）。
    """
    if os.path.isfile(MAGICK_EXE):
        imdir = os.path.dirname(MAGICK_EXE)
        env = os.environ.copy()
        env["MAGICK_HOME"] = imdir
        env["MAGICK_CONFIGURE_PATH"] = imdir
        env["MAGICK_CODER_MODULE_PATH"] = os.path.join(imdir, "modules", "coders")
        env["MAGICK_FILTER_MODULE_PATH"] = os.path.join(imdir, "modules", "filters")
        env["PATH"] = imdir + os.pathsep + env.get("PATH", "")
        return [MAGICK_EXE], env
    return ["magick"], os.environ.copy()


def _run_magick(src, dst, factor, is_cancelled=None):
    #Triangle 接近游戏实时缩放常用的双线性插值，减少模板与游戏画面的锐化差异。
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    prefix, env = _magick_cmd()
    fd, temp_dst = tempfile.mkstemp(
        prefix="." + os.path.splitext(os.path.basename(dst))[0] + ".",
        suffix=os.path.splitext(dst)[1],
        dir=os.path.dirname(dst),
    )
    os.close(fd)
    os.remove(temp_dst)
    cmd = prefix + [src, "-filter", "Triangle", "-resize", f"{factor * 100:g}%", temp_dst]
    try:
        process = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        deadline = time.monotonic() + 120
        while process.poll() is None:
            if (is_cancelled and is_cancelled()) or time.monotonic() >= deadline:
                process.kill()
                process.wait()
                if is_cancelled and is_cancelled():
                    raise TemplateOperationCancelled("素材缩放已取消")
                raise RuntimeError("ImageMagick 运行超时")
            time.sleep(0.1)
        if process.returncode:
            raise subprocess.CalledProcessError(process.returncode, cmd)
        os.replace(temp_dst, dst)
    finally:
        if os.path.exists(temp_dst):
            os.remove(temp_dst)


def _is_reparse(path):
    #判断 path 是不是 junction/符号链接（reparse point），和 language_switcher._is_link 一致
    try:
        if os.path.islink(path):
            return True
    except OSError:
        pass
    try:
        st = os.lstat(path)
        if getattr(st, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            return True
    except (OSError, AttributeError):
        pass
    return False


def _inside(path, root):
    try:
        return os.path.commonpath((os.path.realpath(path), os.path.realpath(root))) == os.path.realpath(root)
    except (OSError, ValueError):
        return False


def _safe_rel_path(rel):
    if not isinstance(rel, str) or not rel or "\\" in rel:
        return None
    normalized = os.path.normpath(rel.replace("/", os.sep))
    if os.path.isabs(normalized) or normalized == os.pardir or normalized.startswith(os.pardir + os.sep):
        return None
    if not normalized.lower().endswith(IMAGE_EXTS):
        return None
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
    for part in normalized.split(os.sep):
        if ":" in part or part.endswith((" ", ".")) or part.split(".", 1)[0].upper() in reserved:
            return None
    return normalized


def _safe_target_path(dst_dir, rel):
    normalized = _safe_rel_path(rel)
    if normalized is None:
        return None
    target = os.path.abspath(os.path.join(dst_dir, normalized))
    if not _inside(target, dst_dir) or _is_reparse(dst_dir) or _is_reparse(target):
        return None
    current = os.path.abspath(dst_dir)
    for part in normalized.split(os.sep)[:-1]:
        current = os.path.join(current, part)
        if os.path.lexists(current) and _is_reparse(current):
            return None
    return target


def _walk_images(root, errors=None):
    #枚举 root 下所有图片，返回 (绝对路径, 相对 root 的相对路径)
    #不跟随 junction/符号链接：避免把 aim 联接当模板、也防止循环联接造成 os.walk 死循环
    def _onerror(error):
        if errors is not None:
            errors.append(error)

    for dirpath, dirs, files in os.walk(root, onerror=_onerror):
        dirs[:] = [d for d in dirs if not _is_reparse(os.path.join(dirpath, d))]
        for f in files:
            if f.lower().endswith(IMAGE_EXTS):
                full = os.path.join(dirpath, f)
                rel = os.path.relpath(full, root)
                yield full, rel


def _file_hash(path, is_cancelled=None):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            if is_cancelled and is_cancelled():
                raise TemplateOperationCancelled("素材缩放已取消")
            digest.update(chunk)
    return digest.hexdigest()


def _load_manifest(dst_dir):
    path = os.path.join(dst_dir, MANIFEST_NAME)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}, "corrupt"
        result = {}
        for key, value in data.items():
            if _safe_rel_path(key) is None:
                return {}, "corrupt"
            if not isinstance(value, dict) or not all(
                    isinstance(value.get(k), str) for k in ("source", "target", "recipe")):
                return {}, "corrupt"
            result[key] = value
        return result, "ok"
    except FileNotFoundError:
        return {}, "missing"
    except (OSError, ValueError):
        return {}, "corrupt"


def _magick_fingerprint():
    prefix, env = _magick_cmd()
    completed = subprocess.run(
        prefix + ["-version"], check=True, capture_output=True, timeout=15, env=env,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    digest = hashlib.sha256()
    executable = shutil.which(prefix[0]) or prefix[0]
    digest.update(os.path.normcase(os.path.realpath(executable)).encode("utf-8"))
    digest.update(completed.stdout)
    if os.path.isfile(executable):
        digest.update(_file_hash(executable).encode("ascii"))
    return digest.hexdigest()[:16]


def _save_manifest(dst_dir, data):
    path = os.path.join(dst_dir, MANIFEST_NAME)
    fd, temp_path = tempfile.mkstemp(prefix=".source_hashes.", suffix=".tmp", dir=dst_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=True, indent=2, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


#-----------对外功能-----------

def scale_factor(res):
    """
    给定分辨率字符串（如 '1920x1080'），返回相对 2K 源的缩放倍数。
    支持 0.5x（1280x720，下采样）、0.75x（1920x1080，下采样）、1.5x（3840x2160，上采样）；
    比例不是 16:9、或就是 2K 源本身，都返回 None。
    """
    return SCALE_FACTORS.get(res) if isinstance(res, str) else None


def scale_pack(lang, src_res=SOURCE_RES, progress_cb=None, is_cancelled=None, tool_fingerprint=None):
    """
    把某个语言的 2K 源 pack 按倍率缩放到该语言下所有可缩放的分辨率 pack。
    目标不存在或比源文件旧时生成，其余文件跳过。
    返回 (生成张数, 跳过张数, 详情列表)。
    """
    if not isinstance(lang, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", lang) \
            or src_res != SOURCE_RES:
        return 0, 0, ["语言或源分辨率参数无效，跳过"]
    src_dir = os.path.join(LANGUAGE_DIR, lang, f"{lang}_{src_res}")
    lang_dir = os.path.join(LANGUAGE_DIR, lang)
    if not _inside(lang_dir, LANGUAGE_DIR) or not _inside(src_dir, LANGUAGE_DIR) \
            or not os.path.isdir(lang_dir) or not os.path.isdir(src_dir) \
            or _is_reparse(lang_dir) or _is_reparse(src_dir):
        return 0, 0, [f"{lang} 没有安全可用的 {src_res} 源 pack，跳过"]
    if tool_fingerprint is None:
        try:
            tool_fingerprint = _magick_fingerprint()
        except Exception as e:
            return 0, 0, [f"无法确认 ImageMagick 工具链，跳过缩放: {e}"]

    generated = 0
    skipped = 0
    notes = []
    for name in sorted(os.listdir(lang_dir)):
        if is_cancelled and is_cancelled():
            notes.append(f"{lang} 素材缩放已取消")
            break
        prefix = lang + "_"
        if not name.startswith(prefix):
            continue
        res = name[len(prefix):]
        factor = scale_factor(res)
        if factor is None:
            continue   #不支持该倍率（含 2K 源自己）就跳过，不报错
        dst_dir = os.path.join(lang_dir, name)
        if not os.path.isdir(dst_dir) or _is_reparse(dst_dir):
            notes.append(f"跳过不安全的目标 pack: {lang} {res}")
            continue
        manifest, manifest_status = _load_manifest(dst_dir)
        if manifest_status == "corrupt":
            notes.append(f"{lang} {res} 的缩放记录损坏，将按 2K 源重建")
        next_manifest = {}
        source_paths = set()
        scan_errors = []
        if progress_cb:
            progress_cb(f"开始缩放 {lang} {res} {factor}x ...")
        for src_full, rel in _walk_images(src_dir, scan_errors):
            if is_cancelled and is_cancelled():
                scan_errors.append(RuntimeError("素材缩放已取消"))
                break
            rel_key = rel.replace(os.sep, "/")
            dst_full = _safe_target_path(dst_dir, rel_key)
            if dst_full is None or _is_reparse(src_full):
                notes.append(f"跳过不安全路径 {lang} {res} {rel}")
                scan_errors.append(RuntimeError(f"不安全路径: {rel}"))
                continue
            try:
                source_paths.add(rel_key)
                source_hash = _file_hash(src_full, is_cancelled)
                old_record = manifest.get(rel_key, {})
                recipe = f"resize-v{RECIPE_VERSION}:{factor:g}:im-{tool_fingerprint}"
                if os.path.isfile(dst_full) \
                        and old_record.get("source") == source_hash \
                        and old_record.get("recipe") == recipe \
                        and old_record.get("target") == _file_hash(dst_full, is_cancelled):
                    skipped += 1
                    next_manifest[rel_key] = old_record
                    continue
                _run_magick(src_full, dst_full, factor, is_cancelled)
                next_manifest[rel_key] = {
                    "source": source_hash,
                    "target": _file_hash(dst_full, is_cancelled),
                    "recipe": recipe,
                }
                generated += 1
            except subprocess.CalledProcessError as e:
                err = e.stderr.decode("mbcs", "ignore") if e.stderr else str(e)
                notes.append(f"失败 {lang} {res} {rel}: {err.strip()}")
            except TemplateOperationCancelled:
                scan_errors.append(TemplateOperationCancelled("素材缩放已取消"))
                notes.append(f"{lang} {res} 素材缩放已取消")
                break
            except Exception as e:
                notes.append(f"失败 {lang} {res} {rel}: {e}")
        removed = 0
        if scan_errors:
            notes.append(f"{lang} {res} 源目录扫描不完整，跳过失效模板清理")
        #只删除旧 manifest 明确管理过的派生文件；记录缺失/损坏时不能误删用户自定义模板。
        stale_paths = set(manifest) - source_paths if manifest_status == "ok" else set()
        for rel_key in stale_paths if not scan_errors else ():
            dst_full = _safe_target_path(dst_dir, rel_key)
            if dst_full is None:
                if rel_key in manifest:
                    next_manifest[rel_key] = manifest[rel_key]
                notes.append(f"拒绝清理不安全路径 {lang} {res} {rel_key}")
                continue
            if os.path.isfile(dst_full):
                try:
                    os.remove(dst_full)
                    removed += 1
                except OSError as e:
                    if rel_key in manifest:
                        next_manifest[rel_key] = manifest[rel_key]
                    notes.append(f"清理失败 {lang} {res} {rel_key}: {e}")
        if scan_errors:
            for rel_key, record in manifest.items():
                next_manifest.setdefault(rel_key, record)
        try:
            _save_manifest(dst_dir, next_manifest)
        except OSError as e:
            notes.append(f"保存缩放记录失败 {lang} {res}: {e}")
        if removed:
            notes.append(f"{lang} {res} 清理失效模板 {removed} 张")
        notes.append(f"{lang} {res} {factor}x 处理结束")
    return generated, skipped, notes


def scale_all(progress_cb=None, is_cancelled=None):
    """
    扫描 language/ 下所有语言，把每个语言的 2K 模板按倍率缩放到对应分辨率。
    返回一句话总结，供日志框显示。
    """
    if not os.path.isfile(MAGICK_EXE) and not shutil.which("magick"):
        msg = f"没找到 ImageMagick ({MAGICK_EXE})，跳过素材缩放"
        if progress_cb:
            progress_cb(msg)
        return msg
    if not os.path.isdir(LANGUAGE_DIR):
        return "language/ 不存在，跳过素材缩放"

    total_gen = 0
    total_skip = 0
    all_notes = []
    try:
        with template_write_lock(BASE_DIR, timeout=30, is_cancelled=is_cancelled):
            try:
                tool_fingerprint = _magick_fingerprint()
            except Exception as e:
                return f"无法确认 ImageMagick 工具链，已停止缩放: {e}"
            for lang in sorted(os.listdir(LANGUAGE_DIR)):
                if is_cancelled and is_cancelled():
                    all_notes.append("素材缩放已取消")
                    break
                lang_dir = os.path.join(LANGUAGE_DIR, lang)
                if not os.path.isdir(lang_dir) or _is_reparse(lang_dir):
                    continue
                g, s, notes = scale_pack(
                    lang, progress_cb=progress_cb, is_cancelled=is_cancelled,
                    tool_fingerprint=tool_fingerprint,
                )
                total_gen += g
                total_skip += s
                all_notes.extend(notes)
    except TimeoutError as e:
        all_notes.append(str(e))
    except TemplateOperationCancelled as e:
        all_notes.append(str(e))

    summary = f"素材缩放处理结束: 新生成 {total_gen} 张，已存在跳过 {total_skip} 张"
    for n in all_notes:
        summary += "\n  " + n
    return summary


if __name__ == "__main__":
    #单独运行时直接缩放一次，方便排查
    print("BASE_DIR:", BASE_DIR)
    print("MAGICK_EXE:", MAGICK_EXE, "存在:", os.path.isfile(MAGICK_EXE))
    print(scale_all(progress_cb=lambda s: print(s)))
