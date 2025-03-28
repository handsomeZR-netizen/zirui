from PyInstaller.utils.hooks import collect_all, collect_submodules

# 收集所有openai模块中的子模块
hiddenimports = collect_submodules('openai')

# 收集openai中的数据文件
datas, binaries, hiddenimports_2 = collect_all('openai')

# 合并hiddenimports
hiddenimports.extend(hiddenimports_2)

# 手动添加一些常见漏掉的模块
hiddenimports.extend([
    'dataclasses',
    'typing_extensions',
    'json',
    'logging',
    'time',
    'pathlib',
    'urllib3',
    'certifi',
    'idna',
    'charset_normalizer',
]) 