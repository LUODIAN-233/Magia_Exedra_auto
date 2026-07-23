#语言与分辨率切换模块
#这个文件只依赖标准库，不依赖PySide6，方便单独测试
#
#原理：根目录下的 aim/ 不再是真实文件夹，而是一个 Windows 目录联接（junction），
#指向 language/<语言>/<语言>_<分辨率>/ 里的某个真实模板包。
#切换语言/分辨率时，只需把 aim 这个 junction 重新指向目标 pack，真正的模板文件一行都不动。
#所有运行时路径（./aim/...）照常使用，联接对读取透明。
#
#junction 用 cmd 的 mklink /J 创建（不需要管理员权限），用 os.rmdir 删除（只删链接，不删目标内容）。

import os
import sys
import json
import re
import stat
import subprocess
import tempfile
import struct
import zlib

try:
    from src.packs.file_lock import template_write_lock
except ModuleNotFoundError:  #支持直接运行本文件排查
    from file_lock import template_write_lock


def base_dir():
    #脚本位于 src/packs/ 子目录，需再上两层到仓库根；打包后用可执行文件所在目录
    #与 main.py 里 get_executable_directory 的逻辑一致（仅非打包分支多上两层）
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


BASE_DIR = base_dir()
LANGUAGE_DIR = os.path.join(BASE_DIR, "language")
AIM_PATH = os.path.join(BASE_DIR, "aim")                 #根目录的 aim 联接
CONFIG_PATH = os.path.join(LANGUAGE_DIR, "active.json")  #记录当前选择


#语言代码 -> 显示用的中文名。新增语言时在这里加一项，GUI 会自动从这里读取，
#不用改 main.py。找不到的语言代码原样返回。
LANG_LABELS = {'EN': '英语', 'JP': '日语'}


def lang_label(code):
    #语言代码转中文名（找不到返回原代码），供 GUI 显示下拉项和状态文字
    if not code:
        return code
    return LANG_LABELS.get(code, code)


#-----------基础工具-----------

def _pack_dir(lang, res):
    #某个 pack 的真实目录路径，形如 language/EN/EN_1280x720
    return os.path.join(LANGUAGE_DIR, lang, f"{lang}_{res}")


def _valid_pack_id(lang, res):
    if not isinstance(lang, str) or not isinstance(res, str):
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9_-]+", lang) and re.fullmatch(r"[1-9]\d*x[1-9]\d*", res))


def _inside(path, root):
    try:
        return os.path.commonpath((os.path.realpath(path), os.path.realpath(root))) == os.path.realpath(root)
    except (OSError, ValueError):
        return False


def _is_link(path):
    #判断 path 是不是 junction/符号链接（reparse point）
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


def _link_target(path):
    #读取联接真实指向的绝对路径，读不到返回 None
    if not _is_link(path):
        return None
    try:
        return os.path.realpath(path)
    except OSError:
        return None


def _remove_link(path):
    #安全删除联接（只删链接本身，绝不动真实目标里的文件）
    #aim 若是真实目录则拒绝删除，返回 False 让上层提示用户手动处理
    if not os.path.lexists(path):
        return True
    if not _is_link(path):
        return False
    try:
        os.rmdir(path)  #对联接只会删掉链接，不会删目标内容
        return True
    except OSError as e:
        print(f"删除联接失败: {e}")
        return False


def _create_link(link, target):
    #用 mklink /J 创建目录联接，返回 (ok, err_msg)
    try:
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", link, target],
            check=True,
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return True, ""
    except subprocess.CalledProcessError as e:
        msg = e.stderr.decode("mbcs", "ignore") if e.stderr else str(e)
        return False, msg
    except Exception as e:
        return False, str(e)


def pack_usable(lang, res):
    #一个 pack 是否可用：目录存在且至少有一张 png 模板
    if not _valid_pack_id(lang, res):
        return False
    d = _pack_dir(lang, res)
    if not _inside(d, LANGUAGE_DIR) or _is_link(d):
        return False
    if not os.path.isdir(d):
        return False
    for root, dirs, files in os.walk(d):
        dirs[:] = [name for name in dirs if not _is_link(os.path.join(root, name))]
        for filename in files:
            path = os.path.join(root, filename)
            if filename.lower().endswith(".png") and not _is_link(path) and _valid_png(path):
                return True
    return False


def _valid_png(path):
    #完整检查 PNG chunk 长度、CRC、IHDR/IEND，避免截断文件让 pack 被误判为完整。
    try:
        seen_idat = False
        with open(path, "rb") as f:
            if f.read(8) != b"\x89PNG\r\n\x1a\n":
                return False
            first = True
            while True:
                raw_length = f.read(4)
                if len(raw_length) != 4:
                    return False
                length = struct.unpack(">I", raw_length)[0]
                if length > 256 * 1024 * 1024:
                    return False
                chunk_type = f.read(4)
                data = f.read(length)
                raw_crc = f.read(4)
                if len(chunk_type) != 4 or len(data) != length or len(raw_crc) != 4:
                    return False
                if zlib.crc32(chunk_type + data) & 0xffffffff != struct.unpack(">I", raw_crc)[0]:
                    return False
                if first:
                    if chunk_type != b"IHDR" or length != 13 \
                            or not all(v > 0 for v in struct.unpack(">II", data[:8])):
                        return False
                    bit_depth, color_type, compression, filtering, interlace = data[8:13]
                    valid_depths = {
                        0: {1, 2, 4, 8, 16}, 2: {8, 16}, 3: {1, 2, 4, 8},
                        4: {8, 16}, 6: {8, 16},
                    }
                    if bit_depth not in valid_depths.get(color_type, set()) \
                            or compression != 0 or filtering != 0 or interlace not in (0, 1):
                        return False
                    first = False
                elif chunk_type == b"IHDR":
                    return False
                if chunk_type == b"IDAT":
                    seen_idat = True
                if chunk_type == b"IEND":
                    if length != 0 or not seen_idat or f.read(1) != b"":
                        return False
                    break
        #Pillow 是 PyAutoGUI 的运行依赖；verify 会实际解析流并拒绝截断/不可解码 PNG。
        from PIL import Image
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            image.load()
        return True
    except Exception:
        #包含 Pillow 的 DecompressionBombError、解码错误和截断流。
        return False


def validate_template_groups(lang, res, groups):
    """检查模式所需模板组的 _1.png、PNG 头及编号连续性。"""
    if not _valid_pack_id(lang, res):
        return False, ["语言或分辨率格式无效"]
    root = _pack_dir(lang, res)
    if not _inside(root, LANGUAGE_DIR) or _is_link(root) or not os.path.isdir(root):
        return False, ["模板 pack 不存在或路径不安全"]
    errors = []
    for group in groups:
        if not isinstance(group, str) or not group or "\\" in group:
            errors.append(f"模板组路径无效: {group!r}")
            continue
        base = os.path.abspath(os.path.join(root, group.replace("/", os.sep)))
        if not _inside(base, root):
            errors.append(f"模板组越出 pack: {group}")
            continue
        first = base + "_1.png"
        if not os.path.isfile(first) or _is_link(first) or not _valid_png(first):
            errors.append(f"缺失或损坏: {group}_1.png")
            continue
        index = 1
        while os.path.isfile(base + f"_{index}.png"):
            path = base + f"_{index}.png"
            if _is_link(path) or not _valid_png(path):
                errors.append(f"缺失或损坏: {group}_{index}.png")
                break
            index += 1
        parent = os.path.dirname(base)
        prefix = os.path.basename(base) + "_"
        try:
            later = [name for name in os.listdir(parent)
                     if name.startswith(prefix) and name.lower().endswith(".png")]
        except OSError as e:
            errors.append(f"无法读取模板组 {group}: {e}")
            continue
        for name in later:
            suffix = name[len(prefix):-4]
            if suffix.isdigit() and int(suffix) >= index:
                errors.append(f"模板编号不连续: {group}_{index}.png")
                break
    return not errors, errors


#-----------对外功能-----------

def list_packs():
    """
    扫描 language/ 下所有 pack。
    返回 dict: {'EN': [('1280x720', True), ('1920x1080', False), ...], 'JP': [...]}
    key 是语言，value 是 (分辨率字符串, 是否可用) 的列表。
    语言按字母序，分辨率按宽度从大到小排序。
    """
    result = {}
    if not os.path.isdir(LANGUAGE_DIR):
        return result
    for lang in sorted(os.listdir(LANGUAGE_DIR)):
        lang_dir = os.path.join(LANGUAGE_DIR, lang)
        if not os.path.isdir(lang_dir):
            continue
        res_list = []
        for name in os.listdir(lang_dir):
            full = os.path.join(lang_dir, name)
            if not os.path.isdir(full):
                continue
            prefix = lang + "_"
            if not name.startswith(prefix):
                continue
            res = name[len(prefix):]
            res_list.append((res, pack_usable(lang, res)))

        def _key(item):
            try:
                return int(item[0].split("x")[0])
            except Exception:
                return 0
        res_list.sort(key=_key, reverse=True)
        if res_list:
            result[lang] = res_list
    return result


def _read_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        lang, res = data.get("lang"), data.get("res")
        return (lang, res) if _valid_pack_id(lang, res) else (None, None)
    except Exception:
        return None, None


def _write_config(lang, res):
    temp_path = None
    try:
        os.makedirs(LANGUAGE_DIR, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(prefix=".active.", suffix=".tmp", dir=LANGUAGE_DIR)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"lang": lang, "res": res}, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, CONFIG_PATH)
        return True
    except Exception as e:
        print(f"写配置失败: {e}")
        return False
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def current_selection():
    """
    返回当前激活的 (lang, res)。
    只认 aim 联接的实际目标；配置文件仅供 ensure_active() 恢复时使用。
    """
    target = _link_target(AIM_PATH)
    if not target or not os.path.isdir(target) or not _inside(target, LANGUAGE_DIR):
        return None
    target = os.path.normcase(os.path.realpath(target))
    for lang, packs in list_packs().items():
        for res, usable in packs:
            expected = os.path.normcase(os.path.realpath(_pack_dir(lang, res)))
            if target == expected and usable:
                return lang, res
    return None


def switch(lang, res):
    """
    把 aim 联接重指向 language/lang/lang_res。
    返回 (ok: bool, message: str)。
    """
    if not _valid_pack_id(lang, res):
        return False, "语言或分辨率格式无效"
    target = _pack_dir(lang, res)
    if not _inside(target, LANGUAGE_DIR):
        return False, "目标 pack 不在 language/ 内"
    try:
        with template_write_lock(BASE_DIR, timeout=2):
            return _switch_locked(lang, res, target)
    except TimeoutError as e:
        return False, str(e)


def _switch_locked(lang, res, target):
    if not os.path.isdir(target):
        return False, f"目标 pack 不存在: {lang}/{lang}_{res}"
    if not pack_usable(lang, res):
        return False, f"{lang} {res} 这个 pack 是空的（没有模板图片），不能切换"

    #已经是目标了就不用再切
    cur = _link_target(AIM_PATH)
    if cur and os.path.normpath(cur) == os.path.normpath(target):
        if not _write_config(lang, res):
            return True, f"当前已经是 {lang} {res}，但保存选择失败"
        return True, f"当前已经是 {lang} {res}，无需切换"

    #处理现有的 aim：只允许删联接，真目录拒绝（避免误删模板）
    old_target = cur if cur and os.path.isdir(cur) else None
    if os.path.lexists(AIM_PATH):
        if not _is_link(AIM_PATH):
            return False, "aim/ 当前是真实文件夹而不是联接，请先手动把它移走或删掉再切换"
        if not _remove_link(AIM_PATH):
            return False, "移除现有 aim 联接失败"

    ok, err = _create_link(AIM_PATH, target)
    if not ok:
        restore_msg = ""
        if old_target:
            restored, restore_err = _create_link(AIM_PATH, old_target)
            if not restored:
                restore_msg = f"；恢复旧联接也失败: {restore_err}"
        return False, f"创建 aim 联接失败: {err}{restore_msg}"
    actual = _link_target(AIM_PATH)
    if not actual or os.path.normcase(os.path.realpath(actual)) != os.path.normcase(os.path.realpath(target)):
        _remove_link(AIM_PATH)
        if old_target:
            _create_link(AIM_PATH, old_target)
        return False, "创建后的 aim 联接目标校验失败"
    if not _write_config(lang, res):
        return True, f"已切换到 {lang} {res}，但保存选择失败"
    return True, f"切换完成: {lang} {res}"


def ensure_active():
    """
    启动时调用，保证 aim 可用。
    - aim 是有效联接且目标有内容：保持原样
    - aim 缺失或失效：按 config 记录，或退而求其次找第一个可用 pack 来创建联接
    返回 (lang, res, message)，找不到可用 pack 时 lang/res 为 None。
    """
    target = _link_target(AIM_PATH)
    if target and os.path.isdir(target):
        sel = current_selection()
        if sel and pack_usable(sel[0], sel[1]):
            return sel[0], sel[1], f"当前模板: {sel[0]} {sel[1]}"

    #按 config 试着恢复
    lang, res = _read_config()
    if lang and res and pack_usable(lang, res):
        ok, msg = switch(lang, res)
        if ok:
            return lang, res, msg
        return None, None, msg

    #config 不可用，扫一遍找第一个可用 pack
    packs = list_packs()
    errors = []
    for lg in sorted(packs):
        for res, usable in packs[lg]:
            if usable:
                ok, msg = switch(lg, res)
                if ok:
                    return lg, res, msg
                errors.append(msg)
    if errors:
        return None, None, "；".join(errors)
    return None, None, "未找到任何可用的模板 pack（language/ 下的 pack 都没有图片）"


if __name__ == "__main__":
    #单独运行时打印当前状态，方便排查
    print("BASE_DIR:", BASE_DIR)
    print("LANGUAGE_DIR:", LANGUAGE_DIR)
    print("AIM_PATH:", AIM_PATH, "存在:", os.path.lexists(AIM_PATH))
    print("packs:")
    for lg, lst in list_packs().items():
        for res, usable in lst:
            print(f"  {lg} {res}  可用={usable}")
    print("current_selection:", current_selection())
    print("ensure_active:", ensure_active())
