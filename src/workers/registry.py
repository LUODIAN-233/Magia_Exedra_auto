#挂机模式注册表
#目的：让新增挂机模式时不用改 main.py 的 GUI 代码。每个 worker 用 @register 装饰器
#声明自己的显示名、起始界面提示和参数列表，GUI 遍历 REGISTRY 自动生成按钮和参数控件。
#
#参数（ParamSpec）描述一个 worker 启动前需要 GUI 收集的输入：
#  kind='choice'    单选（如 Link Raid 等级），用 QRadioButton 组
#  kind='lp_recover' 喝体力药次数，用 最小/-1/输入/+1/最大 那套控件；显示的是"喝几次"，
#                   传给 worker 时自动 +1（存储语义：1=不喝药，2=喝一次……，见 AGENTS.md）
#  kind='int'       普通整数输入（留作扩展，当前未用）
#以后要加新控件类型，只需在这里加一个 kind，并在 main.py 的 _build_param_widget 里加对应分支。

from dataclasses import dataclass, field
from typing import List, Any
import copy


@dataclass
class ParamSpec:
    #一个 worker 参数的描述，GUI 据此生成控件
    key: str                    #传给 worker 的属性名（worker.lp_recover_times 等）
    label: str                  #控件标题
    kind: str = 'int'           #'choice' | 'lp_recover' | 'int'
    default: Any = 0            #默认值（用户看到的值；lp_recover 也是显示值，不+1）
    min: int = 0                #int / lp_recover 的最小值
    max: int = 10               #int / lp_recover 的最大值
    choices: List[Any] = field(default_factory=list)  #choice 的可选项
    hint: str = ''              #可选的附加说明


@dataclass
class WorkerMeta:
    #一个挂机模式的描述
    name: str                   #模式标识，如 'link_raid'
    label: str                  #启动按钮文字，如 'link raid挂机启动'
    worker_class: type          #BaseWorker 子类
    params: List[ParamSpec]     #参数列表
    start_hint: str = ''        #启动提示（如 '需要在游戏主界面启动'）
    #可使用 {参数名}，启动时按当前 GUI 参数展开，例如 lv{level_choice}
    required_templates: List[str] = field(default_factory=list)


#全局注册表，按注册顺序排列。GUI 遍历它生成控件。
REGISTRY: List[WorkerMeta] = []


def register(name, label, params=None, start_hint='', required_templates=None):
    #装饰器：把一个 BaseWorker 子类注册到 REGISTRY。
    #用法：
    #  @register('link_raid', 'link raid挂机启动',
    #            params=[ParamSpec('level_choice', '...', kind='choice', ...)],
    #            start_hint='需要在游戏主界面启动')
    #  class LinkRaidWorker(BaseWorker): ...
    def decorator(cls):
        if not isinstance(name, str) or not name or any(m.name == name for m in REGISTRY):
            raise ValueError(f'worker 注册名无效或重复: {name!r}')
        specs = list(params or [])
        param_keys = {spec.key for spec in specs}
        for spec in specs:
            if spec.kind not in ('choice', 'lp_recover', 'int'):
                raise ValueError(f'{name}.{spec.key} 的参数类型无效: {spec.kind}')
            if spec.kind == 'choice':
                if not spec.choices or spec.default not in spec.choices:
                    raise ValueError(f'{name}.{spec.key} 的默认选项无效')
            elif not (spec.min <= spec.default <= spec.max):
                raise ValueError(f'{name}.{spec.key} 的默认值不在范围内')
        templates = list(required_templates or [])
        for template in templates:
            if not isinstance(template, str) or not template:
                raise ValueError(f'{name} 的必需模板路径无效')
            try:
                template.format(**{key: 0 for key in param_keys})
            except (KeyError, ValueError) as e:
                raise ValueError(f'{name} 的动态模板路径无效: {template}') from e
        REGISTRY.append(WorkerMeta(
            name=name,
            label=label,
            worker_class=cls,
            params=specs,
            start_hint=start_hint,
            required_templates=templates,
        ))
        return cls
    return decorator


def get_registry():
    #返回注册表副本，避免外部误改内部列表
    return copy.deepcopy(REGISTRY)
